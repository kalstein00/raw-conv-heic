# Issue tracker: GitHub

이슈와 명세는 kalstein00/raw-conv-heic의 GitHub Issues에서 관리한다.
저장소 디렉터리에서 gh CLI를 사용한다.

## 기본 작업

- 생성: gh issue create --title "제목" --body-file <파일>
- 조회: gh issue view <번호> --json number,title,body,labels,comments
- 목록: gh issue list --state open
- 수정: gh issue edit <번호> --body-file <파일>
- 댓글: gh issue comment <번호> --body-file <파일>
- 라벨 추가/제거: gh issue edit <번호> --add-label "라벨" / --remove-label "라벨"
- 종료: gh issue close <번호>

여러 줄의 본문은 UTF-8 임시 파일에 작성해 --body-file로 전달한다.
스킬의 “publish to the issue tracker”는 GitHub 이슈 생성을 뜻한다.
“fetch the relevant ticket”은 해당 이슈 조회를 뜻한다.

## 관계

부모와 자식은 GitHub sub-issue 관계로 연결한다.
선행 조건은 GitHub native issue dependencies로 기록한다.
API의 관계 설정에는 이슈 번호와 database id를 구분한다.
기능을 사용할 수 없으면 본문에 Part of #번호 또는
Blocked by: #번호를 기록하고 부모에도 자식 링크를 남긴다.
모든 선행 이슈가 닫혔는지 확인한 뒤 진행한다.

## Pull requests as a triage surface

PRs as a request surface: no.
