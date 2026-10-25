# 458 — 웹: 탐색기에서 PDF 를 끌어다 놓으면 대기열에 (0.3.475)

## 문제

웹 앱 위에 PDF 를 놓으면 브라우저가 그 PDF 를 탭에서 열어 버렸다.

## 고친 것

- `mobile/lib/platform/web_file_drop_web.dart`: 창의 `dragenter/dragleave/dragover/drop` 을 capture 단계에서 받는다. 파일을 끄는 경우만 (`types` 에 `Files`) 기본 동작을 막는다. 글자 끌기 등은 그대로 둔다.
- 끄는 동안 「여기에 놓으면 대기열에 넣습니다 (PDF)」 안내를 root overlay 에 띄운다.
- 놓은 파일 중 `.pdf` 이고 0보다 크고 50MB 이하인 것만 (`droppablePdf`) 읽어 `enqueuePickedPdfs` 로 넣는다. 「파일에서 추가」와 같은 길과 같은 안내 문구 (`_enqueueFiles`). 나머지는 「건너뜀」 수에 더한다.
- 서재 화면이 붙어 있는 동안 어느 화면 위에 놓아도 된다. 폰은 아무것도 하지 않는다 (stub).

시험: `mobile/test/file_drop_458_test.dart`.
