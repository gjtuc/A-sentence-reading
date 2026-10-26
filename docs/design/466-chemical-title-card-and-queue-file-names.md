# 466 — 화학물질 이름 제목·제목 카드, 대기열에서 빠진 파일 이름 기록

## 증상

『Encyclopedia of Reagents for Organic Synthesis』 항목 PDF의 제목이
"heptanedionato)nickel(II)"로 반만 나왔고, 읽기 화면에 제목 카드(표지)가 없었다.
또 대기열에서 사라진 파일은 이름이 남지 않아 어떤 파일인지 찾을 수 없었다.

## 원인

1. 표지의 큰 글씨 제목은 두 줄이다: "Bis(2,2,6,6-tetramethyl-3,5-" / "heptanedionato)nickel(II)".
   `looks_like_author_dump`는 쉼표가 3개 이상이고 of/for 같은 말이 없으면 저자 목록으로 본다.
   숫자 사이 쉼표(위치 번호)를 세어서 첫 줄과 두 줄 합친 제목이 모두 버려졌다.
2. 제목 카드는 Azure가 문단에 title 역할을 줄 때만 생긴다. 이 양식은 역할이 하나도 없어서
   제목이 다음 줄과 붙어 본문 첫 문장이 됐다.
3. 대기열 펌프는 파일 바이트가 없으면 항목을 지우면서 해시 8자만 남겼다.
   evidence `_safe_details`는 소문자 토큰만 받아 파일 이름은 넣을 수도 없었다.

## 고침

- `looks_like_author_dump`(서버)와 `_titleUsable`(앱): 숫자 사이 쉼표는 세지 않는다.
- `polish_title`: "3,5- heptanedionato"처럼 하이픈 뒤 소문자로 이어진 줄은 붙인다
  ("Pd- and Ni-"처럼 and/or/to 앞은 그대로).
- `align_title_sentences`: 제목 카드가 없고 첫 문장이 고른 제목으로 시작하면 그 앞부분을
  떼어 제목 카드로 만든다(토큰 `split`). 나머지는 같은 id로 본문에 남는다.
- 앱 `removeUploadQueueItem(reason:)`: `upload_queue_remove`에 `reason`
  (bytes_missing | uploaded | fail_or_cancel | other), `file_name`, `bytes_len`, `web`.
- 앱 `clearAll`: 대기열을 지우기 전에 `upload_queue_wiped`(개수, 앞 5개 `file_name_N`).
- evidence(서버·앱): `file_name`, `file_name_0`..`file_name_9` 키만 200자까지 자유 문자열 허용.
  사용자가 고른 파일 이름이지 논문 본문이 아니다. 브라우저는 폴더 경로를 주지 않으므로
  이름이 찾을 수 있는 최대치다.

## 이미 분석된 논문

`analyzed_build`가 바뀌어 보관본을 다시 쓰지 않으므로, 같은 파일을 다시 올리면 새 규칙으로
다시 분석된다. 서버는 원본(`papers/{id}/source.pdf`)과 작업 기록의 `filename`을 보관한다.

## 시험

- `tests/test_design_466_chemical_title_card.py`
- `mobile/test/chemical_title_card_466_test.dart`
