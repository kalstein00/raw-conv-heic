# #2 — Windows 단일 ARW → 독립 검증 HEIC

## 범위와 판정

2026-10-22 Windows CPU에서 실제 Sony A7C II ARW 한 장을 변환했다. HIF 내용은 변환/검증 입력으로 사용하지 않았다. 생성 HEIC의 SDR 기본 이미지, Gain Map, ISO 21496-1 메타데이터와 전체 픽셀 HDR 재구성을 인코더와 별도 구현으로 확인했다.

이는 #2의 Phase 0A 증거다. 자연스러운 톤/색의 최종 수용은 #3, Fold7 내부 화면·Google 포토의 실제 HDR 표시는 #4, 전체 37장 배치는 #5, 깨끗한 Windows에서의 포터블 배포는 #6이다. 이 문서는 ISO 전체 적합성 인증이나 다른 HEIF 변형 지원을 주장하지 않는다.

## 실행 환경과 고정 의존성

Windows 11 Home x64 (10.0.26300), Ryzen 5 5500U, 약 16 GB RAM, Python 3.12.7, uv 0.12.14, VS 2022 Build Tools 17.14.40 / MSVC 14.44.35207. GPU 경로는 비활성화했다.

| 역할 | 고정 버전/커밋 |
| --- | --- |
| RAW 현상 | rawpy 0.27.1 / LibRaw 0.22.1 |
| 수치/미리보기 | NumPy 2.5.4 / Pillow 13.0.0 |
| HEIC 생성 | libultrahdr `47d9f00726adba87e3f04059a50a8b34492e057a` (1.5.2 표기) |
| HEIF 컨테이너 | libheif 1.19.7 `4a3f74bc593ebfc29becc1ed5dd0a61cc66d40e1` + 위 libultrahdr의 PR1503 패치 |
| HEVC 인코더 | x265 `419182243fb2e2dfbe91dfc45a51778cf704f849` (3.4+28) |
| 인코더 측 디코더 의존성 | libde265 `4fb298ec1af0686211dc2def73f4f41c2ce19ce5` |
| 인코더 빌드 의존성 | libjpeg-turbo 3.1.0 `20ade4dea9589515a69793e447a6c6220b464535` |
| 독립 HEVC 디코더 | imageio-ffmpeg 0.6.0의 FFmpeg 7.1 essentials / native HEVC |
| 빌드 | CMake 3.31.10, VS 17 2022 x64 Release, parallel 4 |

Python 패키지는 `uv.lock`으로 고정한다. 네이티브 소스와 Windows 빌드 옵션은 `scripts/build-native.ps1`에 고정했다. upstream 패치의 C++20 designated initializer 한 곳을 같은 필드 순서의 C++17 initializer로 바꾸는 MSVC 호환 수정도 스크립트에 포함한다. CMake 4는 이 x265의 오래된 policy와 맞지 않아 3.31.10을 사용한다. x265 ASM과 libjpeg SIMD는 껐다.

인코더가 libde265를 링크하지만 **독립 검사에서는 호출하지 않는다**. 검사는 Python BMFF 파서 → HEVC NAL 추출 → FFmpeg native HEVC → 별도 NumPy Gain Map 계산 경로다. libheif/libultrahdr의 컨테이너 파서·디코더·HDR 복원 함수는 검사에서 사용하지 않는다. 파일 확장자, `tmap` 존재, 다른 프로세스 실행만으로 성공 처리하지 않는다.

빌드에는 GPL/commercial x265 등 서로 다른 라이선스의 의존성이 있다. 이 개발 환경 증거는 재배포 라이선스 검토나 배포 준비 완료를 의미하지 않는다. 설치 없는 최종 배포 구조도 후속 티켓 범위다.

## 재현

Git, Python 3.12, uv, VS 2022 Build Tools의 Desktop development with C++/Windows SDK가 필요하다. 최초 소스/패키지 다운로드에는 네트워크가 필요하며 변환·검증은 로컬 오프라인으로 실행된다. PowerShell에서 저장소 루트를 작업 디렉터리로 사용한다.

```powershell
uv sync --locked --extra dev --python 3.12
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/build-native.ps1
.venv/Scripts/python.exe scripts/inventory-samples.py C:/path/to/private-samples artifacts/issue-2/inventory.json
.venv/Scripts/python.exe scripts/prove-one.py C:/path/to/private-samples/DSC07773.ARW artifacts/issue-2/DSC07773.heic
```

위 샘플 경로는 자리 표시자다. 자기 ARW 경로로 바꾼다. 출력 HEIC와 `.report.json`, `.sdr.png`는 `artifacts/`에 보관되며 Git에 넣지 않는다. inventory/report/preview가 이미 있으면 다른 출력 이름을 사용한다. 기존 HEIC는 건너뛰고 검증 성공으로 계산하지 않는다. `prove-one.py`는 개발 증거 실행기이며 제품 CLI가 아니다. 보고서는 성공/건너뜀을 JSON으로 출력하고 실패는 오류 종류/메시지와 종료 코드 1로 출력한다.

호출 경계는 `convert_raw(Path, Path)`다. 성공 결과에 출력 경로와 검증 보고서가 포함된다. 예외가 나면 성공 결과를 반환하지 않고 임시 디렉터리를 정리한다. 검증을 통과한 임시 파일만 동일 볼륨 `os.link`로 게시하여 경합 중에도 기존 파일을 덮어쓰지 않는다. 이 PoC는 하드 링크를 지원하는 로컬 파일시스템을 필요로 한다. 원본에 쓰기 작업을 하지 않고 SHA-256·바이트 수·mtime_ns를 전후 비교한다.

## 샘플 조사

37 ARW / 37 HIF, 동일 stem 대응 37쌍, 누락 0. 모든 ARW의 TIFF 모델은 ILCE-7CM2이고 RAW SubIFD는 7040×4688, BitsPerSample 12, Compression 32767, crop origin (12,8), crop size 7008×4672였다. Orientation은 1 또는 8이다. **세부 압축 모드는 미확인**이며 이 숫자나 파일 크기로 무손실/손실/비압축을 단정하지 않는다. TIFF 저장 비트 수 12와 LibRaw 처리 white level 16380, 현상 출력 16bit는 서로 다른 관측값이다.

대표 입력 DSC07773.ARW는 밝은 나뭇잎 틈, 그늘, 인물이 함께 있는 세로 사진이다. 이 한 장으로 모든 촬영 조건을 대표한다고 보지 않는다. LibRaw 처리 크기 7028×4688에서 유효 crop 7008×4672를 취하고 flip=5를 픽셀에 적용해 4672×7008로 저장했다. 독립 SDR 미리보기에서 세로 방향을 확인했다.

현상은 camera WB, linear gamma, auto brightness off, `bright=0.25`, RGB16이다. 이것을 float로 변환한 HDR 의도 이미지와 luminance 기반 Reinhard SDR 의도 이미지를 각각 만든다. HDR은 float16 RGBA로 인코더에 전달한다. SDR은 그 뒤 sRGB 8bit로 양자화한다. 먼저 8bit SDR로 잘라 놓고 확대하는 방식이 아니다. 대표 이미지의 RGB16 중간 단계에서 65535로 포화된 채널은 0이었다. 촬영 시 센서 포화가 없었다는 뜻은 아니다. 고정 노출/톤 정책과 색역 clipping은 PoC용이며 #3의 품질 검토 대상이다.

## 관측 결과

로컬 변환 보고서: `artifacts/issue-2/DSC07773.report.json`. 최종 검증기의 비트 심도/디코더 형식을 포함한 별도 보고서: `artifacts/issue-2/DSC07773.independent.json`. 결과 HEIC는 30,223,251 bytes이며 SHA-256은 `d42a1bc461b3c7979f9bdd280f4019a18cda413b60ad26f9ef92eb70a3ddd46f`이다.

| 항목 | 관측 |
| --- | --- |
| 출력 사진 / Gain Map | 둘 다 4672×7008 |
| SDR coded pixels | HEVC 8bit YUV 4:4:4; FFmpeg `yuv444p` |
| Gain Map coded pixels | HEVC 8bit 단일 채널; FFmpeg `gray` |
| SDR NCLX | BT.709 primaries, sRGB transfer, BT.709 matrix, full range |
| HDR NCLX | BT.709 primaries, linear transfer |
| item 관계 | primary SDR=1, tmap=2 → [1,3], Gain Map=3; altr=[2,1] |
| ISO metadata | version 0, 1 channel, gamma 1, base headroom log2=0, alternate=5.62237644 |
| 전체 독립 복원 | 32,741,376 픽셀, 전부 finite |
| HDR 최고값 | 4.17073965 (SDR reference white=1) |
| reference white 초과 픽셀 | 1,017,186 |
| SDR와 0.01 이상 차이 나는 픽셀 | 20,358,724 |
| 원본 보존 | SHA-256·36,831,232 bytes·mtime_ns 모두 전후 동일 |
| 관측 실행 시간 | 약 75.64초, 해당 개발 환경 1회 관측; 성능 목표/평균 아님 |

`tmap`의 pixi=10은 patched libheif의 derived-item 표기다. 이를 SDR HEVC 10bit라고 보고하지 않는다. 코덱 설정과 실제 FFmpeg 입력 픽셀 형식을 확인한다. HDR 의도는 float16, 독립 복원 계산은 float32다.

독립 검증은 직접 코딩된 hvc1, 단일 tmap, 명시적 NCLX, full-resolution Gain Map, 이미 crop/회전된 픽셀 등 이 인코더의 좁은 출력 부분집합을 지원한다. 지원하지 않는 grid/색 공간/방향 변환/bit depth는 거부한다. ISO 파라미터, item 연결, alternative group, HEVC 디코딩, 픽셀 길이, 유한한 HDR 값까지 확인한다. 최대 headroom의 weight=1에서 `(linear SDR + baseOffset) * 2**(min + gain**(1/gamma) * (max-min)) - alternateOffset`을 인코더와 별도 구현으로 계산한다.

## 검증 절차

```powershell
$env:RAWHDR_SAMPLE='C:/path/to/private-samples/DSC07773.ARW'
$env:RAWHDR_HEIC=(Resolve-Path artifacts/issue-2/DSC07773.heic).Path
.venv/Scripts/python.exe -m mypy src
.venv/Scripts/python.exe -m pytest -q
```

샘플 환경 변수가 없으면 실제 파일 테스트는 skip이다. skip을 실제 변환 성공으로 보고하지 않는다. 실제 테스트는 기존 파일 보존, 손상 RAW의 미게시/임시 정리, 전체 해상도 실제 변환과 독립 복원, 읽기 전용 검사와 손상 tmap 거부, Gain Map/tmap의 미지원 회전·반사·crop 6가지와 알 수 없는 essential property 거부를 확인한다. 개발 중 빈 seam에서 실제 변환 테스트의 실패 → 구현 후 통과, 독립 검사 부수 파일 생성 테스트의 실패 → 읽기 전용 기본 동작으로 수정 후 통과를 확인했다.

네이티브 빌드 스크립트는 이 Windows 개발 환경에서 재실행 성공했다. 초기부터 깨끗한 별도 Windows 설치에서 실행한 증거는 아니다. Standards 리뷰의 P2 1건(미지원 Gain Map 변환 무시)은 실제 HEIC 변형 회귀 테스트에서 재현 후 수정했고 재리뷰에서 해결을 확인했다. Spec 리뷰는 #2 범위의 차단 결함 0건이다. 최종 전체 테스트는 실제 ARW/HEIC 환경 변수를 지정한 상태에서 **11 passed, 0 skipped (78.79초)**였고 `mypy src`는 4개 소스 파일 모두 통과했다. 새 libheif checkout에 upstream 패치를 적용하는 경로와 MSVC 호환 수정이 정확히 한 곳에 일치함도 확인했다.

## 참조

- [고정 libultrahdr HEIF 구현](https://github.com/google/libultrahdr/blob/47d9f00726adba87e3f04059a50a8b34492e057a/lib/src/heifultrahdr.cpp)
- [고정 upstream libheif 패치](https://github.com/google/libultrahdr/blob/47d9f00726adba87e3f04059a50a8b34492e057a/cmake/patches/libheif_pr1503.patch)
- [Android Gain Map 복원 설명](https://developer.android.com/media/platform/hdr-image-format): 복원 식의 참고이며 HEIC 컨테이너 유효성의 대체 증거가 아님.
