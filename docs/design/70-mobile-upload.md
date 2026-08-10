# 70 — Flutter 단일 PDF 업로드 (클라우드)

모듈: `mobile/lib/api/client.dart` · `ingest_models.dart` · `library_controller.dart` · `library_screen.dart`  
서버: 기존 `POST /api/ingest` · `GET /api/ingest/jobs/{id}` · GCS `users/{uid}/papers/…`  
받침: [62-mobile-library.md](62-mobile-library.md) · [18-paper-library.md](18-paper-library.md) · [33](33-mobile-flutter.md)

## 무엇을

Android 앱 **보관**에서 PDF **한 파일**을 골라 Cloud Run ingest → 로그인 사용자 GCS 보관함에 저장하고 목록을 갱신한다.

| 포함 | 미포함 (후속) |
|------|----------------|
| `file_picker` 단일 PDF | 여러 파일 선택 |
| multipart `file` → `/api/ingest` + job poll | 이어올리기 → [71](71-mobile-upload-resume.md) |
| 진행률 UI · 실패 시 에러만 (빈 성공 금지) | docx 앱 업로드 |
| status `mobile_upload` | Play 릴리스 키스토어 |
| 목록 격리 보강 (auth+no UID → empty; personal GCS만 merge) | |

## Flows

1. 로그인 + access allowed (기존 paid gate)
2. 보관 → **PDF 가져오기** → SAF 파일 선택 (1개)
3. 클라이언트: 빈/비PDF/50MB초과/무세션 거절
4. `POST /api/ingest` (Cookie `asr_session`) → poll job (진행 UI: 처리 중 · 끝나면 클라우드 자동 저장)
5. 성공 → GCS 보관은 ingest 경로에서 **이미 강제** → 목록 refresh → **자동으로 해당 논문 open** (읽기 탭)
6. 사용자는 처리 후 다시「PDF 올리기」를 누르지 않음
7. 실패·타임아웃·job 404 → 스낵바/에러 문구만 · 가짜 행 없음

## INVARIANT

- 서버 user는 세션에서만 (바디 `user_id` 없음)
- 앱에 Gemini/GCS secret 없음
- Live Enable / IPS → Trading Gate (ASR 밖)

## EDGE

- 선택 취소 → 침묵
- SAF가 bytes 미제공 → 실패 메시지
- job 인스턴스 유실(404) → 재시도 안내, 성공 위장 금지
- 로그아웃 중 업로드 UI 비활성 · `clearAll`이 upload 상태도 지움
- job `done` but no `cache_id` (짧은 제목 skip 등) → 실패 메시지 (빈 성공 금지)
- DocumentsUI **미리보기** 탭은 PDF를 `VIEW`로 열어 **연결 프로그램** 창이 뜸 — 업로드 선택 시 제목/행을 누를 것 (미리보기 아이콘 금지)

## 킬스위치 · 롤백

- Access gate / 로그아웃 → ingest 401/403
- status `mobile_upload` (계약) · 문제 시 revert PR
- Cloud Run paid/Gemini off 시 ingest 자체가 실패 → 목록 불변

## Device E2E (Samsung · 0.2.94)

1. 로그인 → 보관 (`versionName=0.2.94`)
2. **PDF 가져오기** → DocumentsUI 루트 → **다운로드** → `asr_e2e_small.pdf` (제목 탭; 미리보기/연결 프로그램 창 회피)
3. 진행률(처리 중 · 자동 저장) → 목록에 등장 + **자동으로 읽기 탭 open** (추가 「올리기」 탭 없음)
4. (참고) 대형 OCR PDF는 Cloud Run job이 수분 걸릴 수 있음 — 타임아웃 시 실패 문구, 빈 성공 금지
5. 로그아웃 → 로그인 전용 셸 (PDF 올리기/목록 잔여 없음)

Do not paste paper titles that identify people, emails, or session cookies into chat/PR.

## Version pin

Web/mobile **0.2.94** · `mobile_upload: true` · pubspec `0.2.94+1`
