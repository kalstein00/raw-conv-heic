# #4: 색감 승인 후 HDR 효과 부재 진단

2026-10-23 사용자 확인: v2의 색감은 원본과 같아졌으나 JPEG만 Ultra HDR로 표시되고, HIF/HEIC/JPEG 세 사진이 사실상 같아 보였다. 갤럭시 촬영 사진처럼 하늘이 밝게 빛나는 효과는 없었다. 색감 개선과 HDR 감상 성공을 구분하며 **#4는 계속 미통과**다.

사용자가 제공한 갤럭시 HEIC 원본은 같은 Google 포토 앱에서 실제 HDR로 보이고 PC에서는 그렇게 보이지 않는 비교 기준이다. 파일은 로컬에서만 분석했으며 원본을 변경하거나 GitHub에 올리지 않았다.

## 확인된 두 문제

1. 생성 파일의 실제 최대값은 약 4× SDR 백색인데, 기본 HDR display headroom은 49.261×였다. 현재 `-D 0` realtime 인코딩은 `-k/-K` 권고값과 별개로 선형 HDR 입력의 기본 10,000nit headroom을 사용한다. 고정 소스 `jpegr.cpp`의 one-pass 경로와 `ultrahdr_app.cpp`의 `-L` 옵션에서 확인했다. 기존 독립 검사는 전체 효과(weight=1)만 재구성해 이 문제를 놓쳤다.
2. HDR 대상 선택이 원래 RAW 휘도에 보수적으로 묶여 있어 DSC07793/DSC07796/DSC07805에서 SDR 백색 초과 픽셀이 거의 없다. 이 문제는 headroom과 별개다. 이번 v3은 원인 분리를 위해 HDR 대상 영역이나 승인된 SDR 색감을 바꾸지 않는다. 모든 사진에서 눈에 보이는 HDR 효과를 구현했다고 하지 않는다.

갤럭시 기준 파일의 표준 tmap headroom은 log2 2.3, 즉 약 4.925×다. ICC는 `DCI-P3 D65 Gamut with sRGB Transfer`다. 기본 이미지와 Gain Map은 grid 구조이며 Gain Map은 1000×750, 기본 이미지는 4000×3000이다. 표준 tmap/altr와 함께 Samsung auxC/auxl 연결도 존재한다. 생성 파일은 BT.709/sRGB, 직접 부호화한 전체 해상도 이미지/단색 Gain Map이다. **이 차이 중 어느 것이 Google 포토 HEIC 인식에 결정적인지는 아직 미확인**이다. 색역과 HDR 밝기 확장을 같은 기능으로 취급하지 않는다.

## v3의 제한된 수정과 재현

`convert_raw`의 encoder 명령에 `-L 812`를 추가했다. 203nit 기준 SDR 백색의 4배로, 현재 HDR 의도에 맞춘다. 기기의 실제 nit 밝기를 측정하거나 강제하는 값은 아니다.

실제 ARW 변환 회귀 테스트에서 `alternate_headroom_log2 == 2.0`를 먼저 추가했고, 기존 코드가 5.622376으로 실패하는 것을 확인했다(69.78초). 수정 후 같은 테스트가 통과했다(69.91초). 독립 검증은 2× display headroom에서의 gain weight와 최대값도 별도 `simulated_2x_display_*` 필드로 보고한다.

| DSC07809 | v2 | v3 |
|---|---:|---:|
| alternate headroom log2 | 5.622376 | 2.0 |
| 2× 화면을 가정한 weight | 0.177861 | 0.5 |
| 2× 화면을 가정한 최대값 | 1.280638 | 2.004453 |
| full-weight 최대값 | 4.017831 | 4.017831 |

**v2/v3 HEIC의 기본 이미지와 Gain Map 압축 item 바이트가 각각 완전히 동일함을 확인했다.** 이 비교에서 바뀐 것은 headroom 메타데이터이며, 실제 Fold7 표시 성공은 위 계산으로 입증되지 않는다.

JPEG 자체 probe에서도 `hdrCapacityMax=4`를 확인했다. `maxContentBoost=49.2611`은 realtime 경로의 Gain Map 부호화 범위로 남으며, 화면 적용 기준인 capacity와 구분한다. JPEG probe는 독립 HDR 디코딩 증거로 계산하지 않는다.

실제 샘플 환경 변수를 설정한 전체 테스트는 **14 passed, 0 skipped, 309.50초**였다. `mypy src`는 5개 파일 통과했고, Standards/Spec 분리 검토의 구현 결함은 각각 0건이었다. ARW/HIF 무변경도 확인했다. 전체 제품의 화질·실기기 HDR 수용 통과라는 의미는 아니다.

## HEIC 인식 경로를 나누는 비제품 비교 자료

갤럭시 원본에서 아래 두 진단용 파생 파일을 만들었다. 삼성 전용 형식을 생성 파일에 복제하지 않는다.

- `galaxy-no-aux-control.heic`: auxC/auxl만 제거. Exif/XMP는 유지.
- `galaxy-iso-control.heic`: 앞 파일에서 Exif/XMP 항목과 연결도 제거. 표준 image/grid/tmap, ICC, 방향, altr는 유지.

두 파일 모두 원본과 SDR 디코딩 픽셀이 완전히 같다. 유지된 모든 image/grid/tmap item의 바이트 동일성도 확인했고, 원본의 SHA-256/mtime 무변경을 확인했다. private prototype은 `artifacts/issue-4/prepare-iso-control.py`에 보관한다. 이는 제품 인코더 출력이나 grid/P3에 대한 독립 HDR 검증 완료 자료가 아니다. 사람이 같은 Google 포토에서 원본과 비교해야 한다. 결과가 달라져도 모든 앱의 ISO 지원 여부로 일반화하지 않는다.

로컬 `artifacts/issue-4/fold7-hdr-isolation-v3.zip`은 갤럭시 원본/두 비교 파일, DSC07809-v3 HEIC/JPEG, README를 포함한다. 50,831,931 bytes이며 ZIP CRC 검사를 통과했다. SHA-256: `037f8eab7ca7f25e3f9e7358e634e96eec7fe10f5f4d9b13ee89f67c1df152ce`.

사용자에게 세 갤럭시 파일의 실제 하늘 밝기, v3 JPEG의 v2 대비 차이, v3 HEIC의 HDR 인식 표시와 실제 밝기 확장을 각각 확인하도록 요청했다. 사용자 선택은 HEIC 목표 유지이며 #5 이후의 선행 게이트는 변경하지 않았다.
