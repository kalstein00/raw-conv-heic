"""Independent container inspection, FFmpeg HEVC decode, and gain-map math."""

import re
import subprocess
from pathlib import Path
from typing import Any

import imageio_ffmpeg
import numpy as np
from numpy.typing import NDArray
from PIL import Image

from ._bmff import HeifFile, Reader, VerificationError, read_heif


def _metadata(payload: bytes) -> dict[str, Any]:
    r = Reader(payload)
    if r.number(1) != 0 or r.number(2) != 0:
        raise VerificationError("Unsupported tmap/ISO minimum version")
    writer_version, flags = r.number(2), r.number(1)
    if flags & 4 or flags & 0x33:
        raise VerificationError("Backward direction or unknown ISO flags unsupported")
    channels = 3 if flags & 128 else 1
    common = r.number(4) if flags & 8 else None

    def fraction(signed: bool = False) -> float:
        numerator = r.number(4, signed=signed)
        denominator = common if common is not None else r.number(4)
        if denominator == 0:
            raise VerificationError("Zero ISO metadata denominator")
        return numerator / denominator

    base_headroom, alternate_headroom = fraction(), fraction()
    parameters = [[fraction(True), fraction(True), fraction(), fraction(True), fraction(True)] for _ in range(channels)]
    if r.pos != len(payload):
        raise VerificationError("Unexpected trailing ISO metadata")
    if alternate_headroom <= base_headroom:
        raise VerificationError("No forward HDR headroom")
    for minimum, maximum, gamma, base_offset, alternate_offset in parameters:
        if maximum < minimum or gamma <= 0 or min(base_offset, alternate_offset) < 0:
            raise VerificationError("Invalid gain-map parameters")
    return {"writer_version": writer_version, "channels": channels,
            "use_base_color_space": bool(flags & 64), "base_headroom_log2": base_headroom,
            "alternate_headroom_log2": alternate_headroom, "parameters": parameters}


def _decode(container: HeifFile, item: int, *, gray: bool) -> tuple[NDArray[np.uint8], str]:
    width, height = container.dimensions(item)
    primaries, transfer, matrix, full_range = container.nclx(item)
    if matrix not in (1, 6):
        raise VerificationError("Unsupported YCbCr matrix")
    matrix_name = "bt709" if matrix == 1 else "bt601"
    range_name = "pc" if full_range else "tv"
    command = [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-v", "info", "-xerror", "-threads", "2",
               "-f", "hevc", "-i", "pipe:0", "-frames:v", "1", "-vf",
               f"scale=in_color_matrix={matrix_name}:in_range={range_name}:out_range=pc",
               "-pix_fmt", "gray" if gray else "rgb24", "-f", "rawvideo", "pipe:1"]
    completed = subprocess.run(command, input=container.annex_b(item), capture_output=True, timeout=180)
    if completed.returncode:
        raise VerificationError("Independent HEVC decode failed: " + completed.stderr.decode("utf-8", errors="replace")[-2000:])
    description = completed.stderr.decode("utf-8", errors="replace")
    coded_format = re.search(r"Video: hevc \([^)]*\), ([a-z0-9]+)[(,]", description)
    allowed = {"gray"} if gray else {"yuv420p", "yuv422p", "yuv444p"}
    if coded_format is None or coded_format[1] not in allowed:
        raise VerificationError("HEVC decoder did not confirm the expected 8-bit format")
    channels = 1 if gray else 3
    if len(completed.stdout) != width * height * channels:
        raise VerificationError("HEVC decoded dimensions disagree with HEIF properties")
    return np.frombuffer(completed.stdout, dtype=np.uint8).reshape(height, width, channels), coded_format[1]


def verify_heic(path: Path, *, preview_path: Path | None = None,
                hdr_preview_path: Path | None = None, preview_max_size: int = 1600) -> dict[str, Any]:
    """Verify the supported HEIC subset; optional SDR preview uses no-clobber creation."""
    container = read_heif(path)
    tone_maps = [item for item, kind in container.types.items() if kind == b"tmap"]
    if len(tone_maps) != 1:
        raise VerificationError("Expected exactly one tone-map item")
    tone_map = tone_maps[0]
    refs = container.references.get(tone_map, [])
    if len(refs) != 2 or refs[0] != container.primary or refs[0] == refs[1]:
        raise VerificationError("tmap must reference primary SDR then a distinct gain map")
    base, gain = refs
    if not any(group == [tone_map, base] for group in container.alternatives):
        raise VerificationError("Missing HDR/SDR alternative presentation group")
    width, height = container.dimensions(base)
    if container.dimensions(tone_map) != (width, height):
        raise VerificationError("Derived image size differs from base")
    if any(p.kind in (b"irot", b"imir", b"clap") for item in (base, gain, tone_map) for p in container.properties[item]):
        raise VerificationError("Verifier requires already oriented and cropped pixels")
    base_color = container.nclx(base)
    hdr_color = container.nclx(tone_map)
    if base_color[:2] != (1, 13) or hdr_color[0] != 1 or hdr_color[1] != 8:
        raise VerificationError("PoC verifier requires BT.709 sRGB base and linear BT.709 HDR")
    if container.bit_depths(base) != [8, 8, 8]:
        raise VerificationError("PoC verifier supports an 8-bit SDR base only")
    metadata = _metadata(container.items[tone_map])
    # Both image intents have the same primaries; either metadata color-space
    # selector therefore means linear BT.709, without an implicit matrix change.
    sdr, base_format = _decode(container, base, gray=False)
    single_channel = metadata["channels"] == 1
    gain_pixels, gain_format = _decode(container, gain, gray=single_channel)
    if gain_pixels.shape[:2] != (height, width):
        raise VerificationError("PoC verifier requires a full-resolution gain map")
    params = np.asarray(metadata["parameters"], dtype=np.float32)
    minimum, maximum, gamma, base_offset, alternate_offset = params.T
    hdr_max = 0.0
    changed_pixels = 0
    above_white = 0
    diagnostic = np.empty(((height + 3) // 4, (width + 3) // 4, 3), dtype=np.uint8) if hdr_preview_path else None
    shadow_error_sum = 0.0
    shadow_count = 0
    # Compute every pixel in bounded strips; no libultrahdr gain-map routine is
    # used. Full target headroom has weight=1 in the ISO/Adobe gain-map equation.
    for row in range(0, height, 128):
        encoded = sdr[row : row + 128].astype(np.float32) / 255.0
        linear = np.where(encoded <= 0.04045, encoded / 12.92, ((encoded + 0.055) / 1.055) ** 2.4)
        g = gain_pixels[row : row + 128].astype(np.float32) / 255.0
        logarithmic_gain = minimum + np.power(g, 1.0 / gamma) * (maximum - minimum)
        hdr = (linear + base_offset) * np.exp2(logarithmic_gain) - alternate_offset
        if not np.isfinite(hdr).all() or float(hdr.min()) < -0.01:
            raise VerificationError("Non-finite or invalid reconstructed HDR")
        if diagnostic is not None:
            reduced = np.clip(hdr[::4, ::4] / 4.0, 0, 1)
            encoded_diagnostic = np.where(reduced <= 0.0031308, reduced * 12.92,
                                          1.055 * reduced ** (1 / 2.4) - 0.055)
            diagnostic[row // 4:(row + hdr.shape[0] + 3) // 4] = np.rint(encoded_diagnostic * 255).astype(np.uint8)
        shadow = (linear @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)) < 0.25
        shadow_error_sum += float(np.sum(np.abs(hdr - linear)[shadow], dtype=np.float64))
        shadow_count += int(np.count_nonzero(shadow)) * 3
        hdr_max = max(hdr_max, float(hdr.max()))
        changed_pixels += int(np.count_nonzero(np.max(np.abs(hdr - linear), axis=2) > 0.01))
        above_white += int(np.count_nonzero(np.max(hdr, axis=2) > 1.0))
    if preview_path is not None:
        preview = Image.fromarray(sdr)
        preview.thumbnail((preview_max_size, preview_max_size))
        with preview_path.open("xb") as stream:
            preview.save(stream, format="PNG")
    if hdr_preview_path is not None and diagnostic is not None:
        with hdr_preview_path.open("xb") as stream:
            Image.fromarray(diagnostic).save(stream, format="PNG")
    return {"decoder": "FFmpeg native HEVC + independent ISO reconstruction",
            "ffmpeg_version": imageio_ffmpeg.get_ffmpeg_version(),
            "width": width, "height": height, "sdr_bits": 8, "gain_map_bits": 8,
            "decoded_base_format": base_format, "decoded_gain_map_format": gain_format,
            "gain_map_present": True, "gain_map_dimensions": list(container.dimensions(gain)),
            "tmap_item": tone_map, "base_item": base, "gain_map_item": gain,
            "base_nclx": list(base_color), "hdr_nclx": list(hdr_color),
            "metadata": metadata, "hdr_finite": True, "hdr_max": hdr_max,
            "hdr_above_sdr_white_pixels": above_white, "changed_pixels": changed_pixels,
            "decoded_pixels": width * height,
            "shadow_mean_abs_change": shadow_error_sum / max(1, shadow_count),
            "has_pixels_above_sdr_white": above_white > 0}
