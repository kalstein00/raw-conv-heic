# raw-conv-heic

Sony ARW → Gain Map HEIC 변환 프로젝트. 현재 구현은 [#2](https://github.com/kalstein00/raw-conv-heic/issues/2)의 Windows CPU 단일 파일 기술 검증이다.

- 실행 및 검증 결과: [issue-2 기술 검증](docs/evidence/issue-2.md)
- 호출 경계: `rawhdr.convert_raw(source, output)` → `ConversionResult`
- 독립 파일 검증: `rawhdr.verify_heic(path)` → 검사 보고서

GUI, 배치 제품, Fold7/Google 포토 HDR 표시 검증은 아직 구현/완료하지 않았다. 사진·임시 파일·빌드 도구는 로컬의 무시된 디렉터리에만 둔다.
