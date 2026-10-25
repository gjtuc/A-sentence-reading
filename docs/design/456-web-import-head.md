# 456 — 웹 논문 가져오기: 제목·추정 메인/SI·SI 찾아보기·폴더 변경 (0.3.475)

## 문제

웹에서 「논문 가져오기」로 폴더를 열면 파일 이름만 나왔다. 제목, 「추정 메인 / 추정 SI」, 「SI 찾아보기」가 모두 비었다.
웹 `extractPdfHead` 가 `unsupported` 를 돌려줬기 때문이다. 폰은 PdfBox(`PdfHeadExtract.kt`)로 첫 쪽 글자와 글자 크기를 읽는다.
「폴더 변경」은 저장해 둔 폴더를 그대로 다시 열어서, 다른 폴더로 바꿀 수 없었다.

## 고친 것

- `mobile/web/pdfjs/`: pdf.js 3.11.174 (UMD, Apache-2.0 `LICENSE`)와 `asr_pdf_head.js`.
  `asrPdfHead(buffer, maxPages, maxChars)` 는 폰과 같은 모양 `{ok, headText, infoTitle, pageCount, truncated, code, headLines}` 를 돌려준다.
  줄은 y 2.2pt 안이면 한 줄로 묶고, 크기는 `hypot(t[2], t[3])`, 굵기는 글꼴 이름으로 본다. 실패해도 reject 하지 않는다 (`no_pdfjs`, `encrypted`, `parse_fail`).
- pdf.js 는 가져오기 화면에서 처음 쓸 때만 읽는다 (`_loadPdfjs`). worker 는 `document.baseURI` 기준 (`/app/`).
- 웹 `extractDocxHead` 는 `archive` 패키지로 DOCX 를 풀어 `docxHeadFromBytes` (`mobile/lib/pdf/docx_head.dart`)로 읽는다.
- 웹 NFKC 는 브라우저 `String.normalize`.
- 「폴더 변경」은 `change: true` 로 `showDirectoryPicker` 를 항상 띄우고, 예전 폴더에서 시작한다 (`startIn`).

## 메인 + SI 짝

- SI 제목이 저자 줄과 같은 글꼴이라 저작권 줄을 제목으로 잡던 것: `looksLikeAuthorLine` 에 이름 단어만 있는 줄 규칙을 더했다 (이니셜 + 쉼표 2개, 또는 별표 + `and`).
- 제목으로 짝이 안 맞아도 DOI 가 같고 메인 하나 + SI 하나면 세트로 묶는다. SI 는 메인의 제목을 빌린다.

## 확인

`scripts/pdf_head_probe.py` — 헤드리스 크롬에서 pdf.js 로 읽고 `.cache/pdf_head/<stem>.json` 에 쓴다. 콘솔에는 개수만 찍는다.
시험: `mobile/test/web_import_456_test.dart`.
