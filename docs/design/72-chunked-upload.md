# 72 — Chunked PDF upload (byte-range resume)

모듈: `ingest_chunked.py` · `app.py` `/api/ingest/uploads*` · `client.dart` · `library_controller.dart`  
받침: [71-mobile-upload-resume.md](71-mobile-upload-resume.md) · [70-mobile-upload.md](70-mobile-upload.md)

## 무엇을

모든 PDF를 **256KiB 조각**으로 올려, 전송 중 끊김 시 **이미 받은 offset부터** 이어 보낸다.  
같은 파일 재선택·앱 자동 재개 시 **이전 조각 무결성(`prefix_sha256`) 확인 후**에만 이어간다.

| 포함 | 미포함 (후속) |
|------|----------------|
| `POST/GET/PUT …/uploads` · `…/complete` | tus 프로토콜 전체 |
| 모든 PDF 조각화 (크기 무관) | docx 조각 업로드 |
| `prefix_sha256` 무결성 · 불일치 시 세션 폐기 | OS 백그라운드 알림 |
| owner 세션 인가 · 교차 유저 404 | Cloud Run 처리 워커 페일오버 |
| status `ingest_chunked_upload` | Content-Range 헤더 (query `offset` 사용) |

## Flows

1. `POST /api/ingest/uploads` `{filename, content_hash, size}` → `upload_id`, `chunk_size`, `received_offset=0`
2. `PUT /api/ingest/uploads/{id}?offset=N` + raw body + `X-Chunk-Sha256` → 연속 offset만 허용
3. 끊김 → 앱 draft의 `upload_id`로 `GET` → 로컬 `sha256(bytes[0:offset]) == prefix_sha256` 일 때만 PUT 재개
4. 불일치·사이즈/해시 불일치 → draft wipe · **처음부터** (빈 성공·이어붙이기 금지)
5. `POST …/complete` → 조립 · full `content_hash` 검증 · 기존 ingest job 시작 · chunk 객체 삭제

## INVARIANT

- user = 세션 UID만 (`owner_uid` 서버 기록)
- 앱에 GCS/Gemini secret 없음
- Live Enable / IPS — **이번 칩 불필요** (Trading Gate)

## Kill / rollback

- `ASR_CHUNKED_UPLOAD=0` → create 503 · 앱은 multipart 폴백
- Revert PR · status 키 무시(구 클라)

## Version

Web/mobile **0.2.89** · pubspec `0.2.89+1`

## Device E2E

1. APK `0.2.89` · live `ingest_chunked_upload: true`
2. PDF 가져오기 → 조각 진행 중 강제 종료 → 재실행 자동 이어올리기(무결성 OK) → 보관 완료
3. (선택) 손상 draft 시뮬레이션 → 처음부터 / 실패 문구, 가짜 성공 없음
4. 로그아웃 → draft 없음

Do not paste emails, cookies, or paper titles into chat/PR.
