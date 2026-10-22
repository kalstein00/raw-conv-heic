# raw-conv-heic

<!-- impeccable:product-schema 1 -->

## Users

카메라 사용자. 카메라 RAW 파일을 HEIC로 변환하려는 사람을 위한 프로그램이다.

## Product Purpose

RAW 파일을 HEIC로 변환한다.

## Capabilities and Constraints

- 제품은 GUI를 제공하는 방향이며, GUI 플랫폼은 아직 결정하지 않았다.
- 대상 운영체제, 기술 스택, 지원 RAW 형식은 미정이다.
- 파일 선택 방식과 일괄 변환 흐름은 미정이다.
- 로컬 처리 여부, 원본 보존 정책, 출력 화질 및 메타데이터 보존 요구사항은 미정이다.

## Evidence on Hand

- `README.md`: 저장소 이름과 RAW → HEIC 변환 목적을 설명한다.
- init 인터뷰에서 사용자가 카메라 사용자를 위한 RAW → HEIC 변환 프로그램임을 확인했다.
- init 시점에 앱 구현과 변환 성능·품질 검증 자료는 없다.

## Open Decisions

- 실행 플랫폼과 GUI 프레임워크를 결정한 뒤 `## Platform`을 추가한다. 현재는 웹 또는 네이티브 플랫폼을 가정하지 않는다.
- 기술 스택 선정은 보류한다. 사용자에게서 특정 스택 선택이나 선정 위임을 받지 않았다.
- 구체적인 사용 흐름과 변환 성공 기준은 후속 제품 설계에서 정한다.
