# 486 — 짧은 제목도 보관함에 넣고, 같은 문서인지는 파일로 가린다

## 문제

제목(정규화한 `title_key`)이 24글자보다 짧으면 `save_paper_session`이 저장을 거부했다. 분석은 끝까지 돌고
"제목이 너무 짧거나 없어 보관함에 넣지 못했습니다"로 실패했다. 심사 기록("REVIEWER COMMENTS"),
"Peer review" 같은 문서가 여기에 걸린다.

24글자 제한의 이유: 업로드 전 캐시 확인(`find_cached_by_text`)은 보관함 제목이 새 파일 앞부분 글에
**들어 있는지**로 같은 문서를 찾는다. 짧은 제목은 남의 문서 앞부분에도 흔히 들어 있어, 다른 문서의
분석 결과가 열린다. 저장 쪽도 같은 제목이면 같은 문서로 보고 덮어쓰거나 목록에서 지웠다.

## 방침

- 제목이 24글자 이상이면 지금처럼 제목 + 형식(pdf/docx) + 역할(본문/보충)이 같은 문서다.
- 짧으면 제목 대신 파일 바이트 SHA-256(`content_hash`)이 같은 문서만 같은 문서다
  (`paper_identity`, `entry_identity`). 해시가 없고 `force_cache_id`도 없으면 예전처럼 저장하지 않는다.
- 이 규칙을 쓰는 곳:
  - 저장 시 기존 행 찾기
  - 저장 끝 목록 정리
  - GCS 목록 합치기(`merge_index_entries`)
- 짧은 제목은 제목으로 짝 찾기(`apply_pairing_pass`)에도, 제목만 주고 지우기(`delete_cached_paper`)에도
  쓰지 않는다.
- `find_cached_by_text`는 원래 짧은 제목을 건너뛴다. 그대로 둔다.
- 앱 변경 없음. 제목 고치기는 다음 단계.

## 확인

`tests/test_design_486_weak_title_identity.py`
