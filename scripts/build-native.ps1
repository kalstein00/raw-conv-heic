# Development-only native build for issue #2. Requires Git, Python 3.12/uv and
# VS 2022 Build Tools (Desktop development with C++ + Windows SDK).
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$tools = Join-Path $root '.tools'
$cmake = Join-Path $root '.venv/Scripts/cmake.exe'
$prefix = Join-Path $tools 'install'
New-Item -ItemType Directory -Force $tools | Out-Null
function Run-Git([string[]]$Arguments) {
  & git @Arguments
  if ($LASTEXITCODE -ne 0) { throw 'Git command failed' }
}
function Source([string]$Name, [string]$Url, [string]$Commit) {
  $path = Join-Path $tools $Name
  if (-not (Test-Path $path)) { Run-Git @('clone', $Url, $path) }
  $head = & git -C $path rev-parse HEAD
  if ($LASTEXITCODE -ne 0) { throw "Invalid source tree: $path" }
  if ($head -ne $Commit) { Run-Git @('-C', $path, 'checkout', '--detach', $Commit) }
}
Source 'libultrahdr' 'https://github.com/google/libultrahdr.git' '47d9f00726adba87e3f04059a50a8b34492e057a'
Source 'libheif' 'https://github.com/strukturag/libheif.git' '4a3f74bc593ebfc29becc1ed5dd0a61cc66d40e1'
Source 'x265' 'https://github.com/videolan/x265.git' '419182243fb2e2dfbe91dfc45a51778cf704f849'
Source 'libde265' 'https://github.com/strukturag/libde265.git' '4fb298ec1af0686211dc2def73f4f41c2ce19ce5'
Source 'libjpeg-turbo' 'https://github.com/libjpeg-turbo/libjpeg-turbo.git' '20ade4dea9589515a69793e447a6c6220b464535'
$heif = Join-Path $tools 'libheif'
$patch = Join-Path $tools 'libultrahdr/cmake/patches/libheif_pr1503.patch'
# A failed reverse check is expected on a fresh checkout. Windows PowerShell
# can promote native stderr to a terminating error under Stop.
$ErrorActionPreference = 'Continue'
& git -C $heif apply --reverse --check $patch 2>$null
$patchAlreadyApplied = $LASTEXITCODE -eq 0
$ErrorActionPreference = 'Stop'
if (-not $patchAlreadyApplied) { Run-Git @('-C', $heif, 'apply', $patch) }
# Upstream patch uses a C++20 designated initializer in a C++17 target.
$encoder = Join-Path $heif 'libheif/plugins/encoder_x265.cc'
$sourceText = [IO.File]::ReadAllText($encoder)
$new = 'return { heif_error_Usage_error, heif_suberror_Unsupported_parameter, encoder->last_error_message.c_str() };'
# Whitespace-independent, exactly one known initializer only.
$pattern = 'return\s*\{\s*\.code\s*=\s*heif_error_Usage_error,\s*\.subcode\s*=\s*heif_suberror_Unsupported_parameter,\s*\.message\s*=\s*encoder->last_error_message\.c_str\(\)\s*\};'
if ($sourceText -match $pattern) {
  [IO.File]::WriteAllText($encoder, [regex]::Replace($sourceText, $pattern, $new))
} elseif ($sourceText -notmatch 'return\s*\{\s*heif_error_Usage_error,\s*heif_suberror_Unsupported_parameter,\s*encoder->last_error_message\.c_str\(\)\s*\};') { throw 'Expected x265 compatibility patch site missing' }
# Keep each HEVC slice below common decoder NAL limits for the verified 33 MP samples.
# This does not change dimensions or claim mobile HDR compatibility.
$slicePatch = Join-Path $PSScriptRoot 'patches/libultrahdr-hevc-slices.patch'
$uhdrSource = Join-Path $tools 'libultrahdr'
$ErrorActionPreference = 'Continue'
& git -C $uhdrSource apply --unidiff-zero --reverse --check $slicePatch 2>$null
$slicePatchApplied = $LASTEXITCODE -eq 0
$ErrorActionPreference = 'Stop'
if (-not $slicePatchApplied) { Run-Git @('-C', $uhdrSource, 'apply', '--unidiff-zero', $slicePatch) }
function Build([string]$Name, [string]$Source, [string[]]$Options, [bool]$Install = $true) {
  $build = Join-Path $tools "build-$Name"
  & $cmake -S $Source -B $build -G 'Visual Studio 17 2022' -A x64 "-DCMAKE_INSTALL_PREFIX=$prefix" @Options
  if ($LASTEXITCODE -ne 0) { throw "$Name configure failed" }
  & $cmake --build $build --config Release --parallel 4
  if ($LASTEXITCODE -ne 0) { throw "$Name build failed" }
  if ($Install) {
    & $cmake --install $build --config Release
    if ($LASTEXITCODE -ne 0) { throw "$Name install failed" }
  }
}
Build 'x265' (Join-Path $tools 'x265/source') @('-DENABLE_ASSEMBLY=OFF','-DENABLE_CLI=OFF','-DENABLE_SHARED=ON')
Build 'de265' (Join-Path $tools 'libde265') @('-DENABLE_SDL=OFF','-DENABLE_DECODER=OFF','-DENABLE_ENCODER=OFF','-DBUILD_SHARED_LIBS=ON')
Build 'jpeg' (Join-Path $tools 'libjpeg-turbo') @('-DWITH_SIMD=OFF','-DENABLE_SHARED=ON','-DWITH_CRT_DLL=ON')
Build 'heif' $heif @("-DCMAKE_PREFIX_PATH=$prefix",'-DBUILD_SHARED_LIBS=ON','-DWITH_EXPERIMENTAL_GAIN_MAP=ON','-DWITH_EXAMPLES=OFF','-DBUILD_TESTING=OFF','-DWITH_GDK_PIXBUF=OFF','-DWITH_LIBSHARPYUV=OFF','-DWITH_HEIFIO=OFF','-DWITH_DOCS=OFF','-DWITH_HEADER_COMPRESSION=OFF','-DENABLE_PLUGIN_LOADING=OFF','-DWITH_AOM_DECODER=OFF','-DWITH_AOM_ENCODER=OFF','-DWITH_DAV1D=OFF','-DWITH_JPEG_DECODER=OFF','-DWITH_JPEG_ENCODER=OFF','-DWITH_OpenJPEG=OFF','-DWITH_OpenJPH=OFF','-DWITH_LIBPNG=OFF','-DWITH_LIBTIFF=OFF','-DWITH_FFMPEG_DECODER=OFF')
Build 'uhdr' (Join-Path $tools 'libultrahdr') @("-DCMAKE_PREFIX_PATH=$prefix",'-DUHDR_BUILD_DEPS=OFF','-DUHDR_ENABLE_HEIF=ON','-DUHDR_BUILD_TESTS=OFF','-DUHDR_ENABLE_GLES=OFF') $false
