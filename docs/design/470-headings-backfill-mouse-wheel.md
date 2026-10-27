# 470 — 소제목이 없는 기기 사본 보충 · 마우스로 돌리는 이동 창

## 증상

0.3.483 배포 뒤 xie-chen 논문을 다시 분석·합쳤는데 PC 창의 "문장으로 이동"에 소제목이 안 나왔다.
서버 보관본(`f38ac518e987`)에는 소제목 13개가 있었다.

## 원인

분석과 합치기를 한 PC 창이 아직 0.3.482였다(증거: `paper_merge_done` `ver=0.3.482`).
옛 앱은 기기 사본을 `readingSessionToPaperDiskJson`으로 다시 쓰면서 `headings`를 몰랐다.
새 앱은 기기 사본을 먼저 연다(design/185, `reader_open` `local_paper_disk`). 그래서 서버에 있는
소제목을 받을 길이 없었다.

## 고침

- 서버 `GET /api/cache/papers/{id}/headings`: 사용자 GCS의 `session.json`에서 소제목 목록만 돌려준다.
  공유 디스크의 남은 사본은 믿지 않는다(design/121). GCS가 꺼졌을 때만 로컬.
- `to_public_dict`는 `headings`를 늘 넣는다(빈 목록도). 앱은 `headingsKnown`으로 "목록을 받은 적 있음"을 안다.
- 앱: 연 논문이 `headingsKnown`이 아니면 한 번 묻고(`_backfillPaperHeadings`), 문장에 펼친 뒤
  기기 사본에 저장한다. 빈 목록도 저장해 다시 묻지 않는다. 실패하면 다음에 열 때 다시 묻는다.
  증거 `paper_headings_backfill`.
- 이동 창(`reader_nav_picker`)은 마우스 끌기로도 돈다. Flutter 기본은 마우스 끌기를 스크롤로 받지 않는다.

## 시험

- `tests/test_design_470_headings_backfill.py`
- `mobile/test/paper_headings_469_test.dart` (design/470 시험 둘)
- `mobile/test/reader_nav_picker_mouse_470_test.dart` (고치기 전 코드에서 실패 확인)
