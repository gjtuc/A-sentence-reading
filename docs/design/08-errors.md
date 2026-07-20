# 08 — Errors

## 코드 목록

| code | HTTP | 사용자 메시지 (ko) | 원인 |
|------|------|-------------------|------|
| `not_implemented` | 501 | 아직 준비 중인 기능입니다. | stub |
| `missing_file` | 422 | PDF 파일을 선택하세요. | multipart 누락 |
| `not_pdf` | 400 | PDF만 올릴 수 있습니다. | MIME/확장자 |
| `invalid_pdf` | 400 | PDF를 열 수 없습니다. | 깨짐 |
| `encrypted_pdf` | 400 | 암호 PDF는 지원하지 않습니다. | |
| `file_too_large` | 413 | 파일이 너무 큽니다 (최대 50MB). | |
| `payload_too_large` | 413 | 문장/그림이 너무 많습니다. | 한도 |
| `extract_timeout` | 504 | 추출 시간이 초과되었습니다. | |
| `session_not_found` | 404 | 세션이 만료되었습니다. 다시 업로드하세요. | |
| `internal` | 500 | 내부 오류입니다. | 로그 확인 |

## warnings (세션은 성공)

문자열 코드, UI에 작게 표시 가능:

| warning | 의미 |
|---------|------|
| `sparse_text` | 텍스트 거의 없음 |
| `no_sentences` | 분할 결과 0 |
| `no_embedded_figures` | 그림 0 |
| `reading_order_unverified` | 다단 미검증 |
| `long_document` | 페이지 많음 |
| `possible_caption_dup` | 캡션 중복 의심 |
| `tiny_images_dropped` | 작은 이미지 필터됨 |

## 로깅

서버: `warning` 이상만 stderr. 파일 내용은 로그에 넣지 않음.
