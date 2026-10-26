# 460 — 웹 끌어다 놓기·파일에서 추가에 Word, 파일 한도 100MB (0.3.476)

## 바란 것

- 웹에 끌어다 놓기(458)와 「파일에서 추가」가 PDF 만 받았다. Word(.docx)도 받는다.
  서버와 대기열(`enqueuePickedPdfs`, `_validateIngestBytes`)은 이미 .docx 를 받았고, 폴더 가져오기도 .docx 를 넣었다. 막힌 곳은 `droppablePdf` 와 file picker `allowedExtensions` 뿐.
- 파일 한도 50MB → 100MB.

## 고친 것

- `droppableDoc`: `.pdf` 또는 `.docx`, 0 초과 100MB 이하. 옛 `.doc` 은 안 받는다 (서버도 안 받음).
- 앱 한도는 `kMaxUploadBytes` (`mobile/lib/api/upload_limits.dart`) 하나. 업로드 검사, 폴더 파일 읽기, 첫 쪽 읽기(제목), 끌어다 놓기, SI 내려받기(`kMateFetchMaxBytes`)가 같은 값을 쓴다.
- 안드로이드 `SafTreeHandler.kt` (`maxReadBytes`, `MAX_BYTES`), `DocxHeadExtract.kt` 도 100MB.
- 서버 `_MAX_UPLOAD_BYTES`, `ingest_chunked._MAX_BYTES`, title-verify 도 100MB.
- 원본 보관 `SOURCE_MAX_BYTES` 80MB → 100MB. 아니면 80MB 넘는 파일은 재분석·기기 옮기기용 원본이 안 남는다.
- 조각 업로드 횟수 한도 `upload_put` 600 → 1200 / 10분 (`ASR_UPLOAD_PUT_MAX`). 100MB 는 256KiB 조각 약 400개라 600 이면 큰 파일 두 개째에 막힌다.

## 남은 위험

모든 파일은 256KiB 조각으로 올라가므로 Cloud Run 요청 32MB 한도와는 무관하다.
분석 worker 는 2Gi 그대로다. 100MB 파일은 /tmp (메모리) + 바이트 사본으로 수백 MB 를 쓴다. OOM 이 보이면 `ASR_WORKER_MEMORY` 를 올린다.

시험: `mobile/test/file_drop_458_test.dart` (design/460 test), `tests/test_pdf_advisory_head_limit_231.py`.

## 옛 Word (.doc) — design/461

.doc (Word 97-2003) 은 ZIP+XML 인 .docx 와 속이 다른 이진 형식이라 python-docx 가 못 읽는다. 이름만 .docx 로 바꿔도 앞 바이트 검사(`PK`)에서 걸린다.
서버 변환(LibreOffice)은 이미지가 수백 MB 커져서 하지 않는다.
끌어다 놓은 .doc 은 「건너뜀」에 섞지 않고 따로 센다 (`isOldWordDoc`, `onFiles` 셋째 값). 8초 안내: Word 에서 「다른 이름으로 저장」→ .docx.
