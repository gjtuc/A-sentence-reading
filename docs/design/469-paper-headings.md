# 469 — 논문의 소제목을 논문마다 한 번만 저장

## 증상

xie-chen 2023(리뷰)을 합친 뒤 "문장으로 이동"이 `Body 168 / Introduction 18 /
Supplementary 2`로 나왔다. 순서가 뒤섞인 것처럼 보였지만 문장 순서는 맞았다.
이동 창이 이름이 같은 구간을 하나로 묶었고(Body 17 + Body 151), 논문의 소제목
("2.1. Metal–Metal Interactions" 등)은 `header_key`의 고정 어휘에 없어 버려졌다.

## 저장 방식

문장마다 소제목을 붙이지 않는다. 세션에 목록 하나만 둔다.

```json
"headings": [{"text": "CONSPECTUS", "from": "sent_000001"},
             {"text": "1. INTRODUCTION", "from": "sent_000018"}, ...]
```

각 항목은 `from` 문장부터 다음 항목 전까지 유효하다. 빈 `text`는 소제목이 끝남을 뜻한다.
이어진 소제목은 ` › `로 잇는다("3. … › 3.1. …"). 제목, 참고문헌, SI 구간에는 붙이지 않는다.
최대 200개, 글자 수 제한은 `clean_headings`.

## 서버

- `section_flow.heading_text`: Azure `sectionHeading` 역할이거나 번호 붙은 제목 꼴이면 소제목.
- `_heading_per_box`가 상자마다 유효한 소제목을 정하고, `_box_marks_for`가 `BoxMark.heading`과
  카드 안에서 새로 시작하는 소제목 `heading_starts`(그 뒤 첫 문장)를 기록한다.
  소제목 상자는 다음 카드에 붙어 있어 카드 첫 문장만으로는 위치를 못 찾기 때문이다.
- `paper_headings.heading_anchors`: 이 표시들을 `assign_boxes`로 문장에 맞춰 목록을 만든다.
  제목과 같은 소제목은 버린다.
- 섹션 구분·순서·`marked_text`는 그대로다. 옛 코드와 새 코드의 `order_boxes` 결과를
  논문 5편에서 비교해 같음을 확인했다(design/302 `live_ok False` 논문이라 덧붙이기만 함).
- 재분석 재개(`skip_debone`)와 SI 단독 분석에는 목록이 없다.

## 앱

- `applyPaperHeadings`가 목록을 문장의 `heading`에 펼친다. 기기 사본은 `paperHeadingsOf`로 되돌려 저장.
- 이동 창은 (구간, 소제목)이 이어지는 묶음 단위다. 이름표는 소제목의 마지막 조각, 없으면 구간 이름.
  옛 논문도 `Body 17 / Introduction 18 / Body 151`처럼 읽는 순서대로 나뉜다.
- 읽기 화면 구분선(design/430)은 소제목이 바뀌는 곳에 소제목 전체를 보인다.
- 책갈피 키는 예전대로 `{구간}:{구간 안 번호}`다. 묶음이 바뀌어도 같은 문장을 가리킨다.

## 시험

- `tests/test_design_469_paper_headings.py`
- `mobile/test/paper_headings_469_test.dart`
