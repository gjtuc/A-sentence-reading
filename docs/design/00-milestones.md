# 00 — Milestones

구현을 **한 번에 다 하지 않는다.** 각 단계가 끝나면 수동/자동으로 검증 가능하게.

## M0 — Skeleton (현재, 완료)

- mock UI, 독립 네비, Immersive식 CSS, PDF stub
- 합격: `/api/status` · `/api/session/mock` · 화살표 동작

## M1 — Data + API 계약 (코드 최소)

**목표:** 실 PDF 없이 계약만 고정.

- `models` 필드를 [01-data-model.md](01-data-model.md)에 맞게 확장 (필요 시)
- `POST /api/ingest` 가 **가짜 성공 경로**를 갖되, 실제 extract 호출 전 스키마만 맞춤  
  (또는 OpenAPI 예제 + Pydantic 모델만 추가)
- `GET /api/session/{session_id}` 추가 (메모리 1개 세션도 가능)
- 합격: 클라이언트와 서버가 같은 JSON 키를 씀 ([04-api-contract.md](04-api-contract.md))

## M2 — PDF 텍스트만

**목표:** 문장 패널에 **진짜 논문 문장**이 보이게.

- `extract_text` 실구현 ([02-pdf-extract.md](02-pdf-extract.md) §텍스트)
- `split_into_sentences` 실구현 ([03-sentence-split.md](03-sentence-split.md))
- ingest → figures는 비어 있어도 됨 / 문장만 채워도 OK
- 합격: 샘플 PDF 1개로 Sent N/M 이 0이 아니고, `Fig.` 가 문장 중간에서 안 끊김 (픽스처)

## M3 — PDF 그림

**목표:** 하단 캐러셀에 추출 그림.

- `extract_figures` ([02](02-pdf-extract.md) §그림)
- 이미지를 `data/extracted/{session_id}/` 에 저장 후 URL로 서빙
- 합격: 샘플 PDF에서 그림 ≥1, 넘기기 가능. 로고/아이콘 대량 혼입은 허용하되 필터 규칙 문서와 일치

## M4 — UI 연결 + 상태

- 파일 선택 → ingest → 세션 로드
- [06-ui-states.md](06-ui-states.md) loading/error/empty
- 합격: mock 없이도 로컬 PDF로 전체 루프

## M5 — 진행 저장 (선택) — 0.2.17

- `localStorage` `asr.progress.v1` + ingest `content_hash` ([21](21-progress-restore.md), [05](05-session-store.md))
- 합격: 새로고침·보관 재열기·같은 파일 재업로드 후 문장/그림 인덱스 복원

## 명시적 연기 (M5 이후)

- ~~compound figure (1a/1b) 분해~~ (0.2.26 — [29-compound-figures.md](29-compound-figures.md))
- ~~Fig. N → 그림 자동 점프 힌트~~ (0.2.25 — [28-fig-ref-jump.md](28-fig-ref-jump.md))
- ~~TTS / 음절 / 품사 색~~ — **하지 않음** (사용자 결정 · 0.2.30 원복). RESEARCH 비목표와 동일.
- ~~다단 reading-order~~ (0.2.32 — [31-reading-order.md](31-reading-order.md); 기하+vision, 로컬 Layout ML 없음)
- ~~GitHub CI · Cloud Run CD~~ (0.2.33 — [32-github-cd.md](32-github-cd.md); `ASR_CD_ENABLED` 게이트)
- **Android Flutter 「문장 읽기」** — 설계 [33-mobile-flutter.md](33-mobile-flutter.md); MVP 나머지(로그인·보관·읽기·TTS) · 스캐폴드 0.2.55 · `android/` 0.2.56
- ~~논문 탭 × 닫기~~ (0.2.42 — [34-tab-close.md](34-tab-close.md); 탭 범위 저장만)
- ~~영→한 단순 번역 + on/off~~ (0.2.43 — [35-translate-simple.md](35-translate-simple.md); 다단계는 후속)
- ~~영→한 다단계 번역~~ (0.2.44 — [36-translate-pipeline.md](36-translate-pipeline.md); draft→sense→polish)
- ~~브라우저 STT 발음 연습~~ (0.2.45 — [37-stt-browser.md](37-stt-browser.md); 점수 없음 · 서버 STT 후속)
- ~~서버 STT~~ (0.2.46 — [38-stt-server.md](38-stt-server.md); Gemini 전사 · 브라우저 폴백)
- ~~번역 EN|KO 좌우 동형~~ (0.2.47 — [39-translate-side-by-side.md](39-translate-side-by-side.md); 전체·축소 공통)
- ~~첨부 시 섹션 번역·요지 재감수·캡션~~ (0.2.48 — [40-ingest-section-translate.md](40-ingest-section-translate.md); live 폴백 유지)
- ~~본문 각주 → References → DOI/Crossref~~ (0.2.49 — [41-cite-ref-open.md](41-cite-ref-open.md); Scholar 폴백)
- ~~읽기 live 번역 제거 · 보관본 번역 백필~~ (0.2.50 — [42-translate-ingest-only.md](42-translate-ingest-only.md))
- ~~섹션 번역 진행 문구 세분화~~ (0.2.51 — [43-translate-progress.md](43-translate-progress.md))
- ~~compound 자동 분리 ingest 끊기~~ (0.2.52 — [44-compound-off.md](44-compound-off.md); rich-v7 · 드래그 크롭만)
- ~~progressive 읽기 열기~~ (0.2.53 — [45-progressive-translate.md](45-progressive-translate.md); 초벌 단계·포커스 고정)
- ~~번역 문장 병렬~~ (0.2.54 — [46-translate-parallel.md](46-translate-parallel.md); 동시 N)
- ~~Flutter `mobile/` 스캐폴드~~ (0.2.55 — [47-flutter-scaffold.md](47-flutter-scaffold.md); [33](33-mobile-flutter.md) 1단계)
- ~~Flutter Android 플랫폼~~ (0.2.56 — [48-flutter-android-platform.md](48-flutter-android-platform.md); `android/` · applicationId)
- ~~각주 표시 정리~~ (0.2.57 — [49-cite-display-clean.md](49-cite-display-clean.md); 박스 [n] 숨김 · FS 칩 hover)
- ~~한글 번역 어절 줄바꿈~~ (0.2.58 — [50-ko-word-wrap.md](50-ko-word-wrap.md); keep-all)
- ~~되새김질 이어 보기~~ (0.2.59 — [51-section-review-flow.md](51-section-review-flow.md); 한 박스)
- ~~되새김질 목소리 이어 듣기~~ (0.2.60 — [52-section-review-voice-seq.md](52-section-review-voice-seq.md))
- ~~되새김질 on/off~~ (0.2.61 — [53-section-review-optional.md](53-section-review-optional.md))
- ~~되새김질 클립 다시 듣기/재녹음~~ (0.2.62 — [54-section-review-voice-clip.md](54-section-review-voice-clip.md))
- ~~되새김질 flow 콕 수정~~ (0.2.63 — [55-section-review-flow-edit.md](55-section-review-flow-edit.md))
- ~~되새김질 키보드~~ (0.2.64 — [56-section-review-keys.md](56-section-review-keys.md))
- ~~되새김질 흰 십자~~ (0.2.65 — [57-section-review-crosshair.md](57-section-review-crosshair.md))
- ~~헤더 파일 열기 + `⋯`~~ (0.2.66 — [58-header-overflow.md](58-header-overflow.md))
- ~~Guide 헤더 배치~~ (0.2.67 — [59-guide-header.md](59-guide-header.md); 기본 밖 · `⋯` 안 옵션)
- ~~패널 단축키 안내 줄 기본 숨김~~ (0.2.82 — [60-panel-hints.md](60-panel-hints.md); Guide에서 다시 켜기)
- ~~Flutter 이메일 로그인·세션~~ (0.2.82 — [61-mobile-email-auth.md](61-mobile-email-auth.md); [33](33-mobile-flutter.md) 로그인 1수단)
- ~~Flutter 보관 목록·open~~ (0.2.82 — [62-mobile-library.md](62-mobile-library.md); [33](33-mobile-flutter.md) 보관)
- ~~Flutter 읽기(문장·그림 독립)~~ (0.2.82 — [63-mobile-reader.md](63-mobile-reader.md); [33](33-mobile-flutter.md) 읽기)
- ~~Flutter TTS (현재 문장)~~ (0.2.82 — [64-mobile-tts.md](64-mobile-tts.md); [33](33-mobile-flutter.md) TTS)
- ~~Flutter Google·카카오 로그인~~ (0.2.82 — [65-mobile-oauth.md](65-mobile-oauth.md); [33](33-mobile-flutter.md) 수단 2–3)
- ~~Flutter 테마 3종~~ (0.2.82 — [66-mobile-theme.md](66-mobile-theme.md); [33](33-mobile-flutter.md) 설정)
- ~~액세스 게이트 (OTP 초대·관리자 Allow/Deny)~~ (0.2.82 — [67-access-gate.md](67-access-gate.md))
- ~~초대 코드 TTL·redeem rate limit~~ (0.2.82 — [67-access-gate.md](67-access-gate.md) Hardening)
- ~~Android Google OAuth SHA-1 런북 · DEVELOPER_ERROR fail-closed~~ (0.2.82 — [65-mobile-oauth.md](65-mobile-oauth.md))
- ~~Android OAuth SHA-1 콘솔 등록 · Google 실기 로그인~~ (0.2.82 — [65-mobile-oauth.md](65-mobile-oauth.md); PC-B SHA-1 실기 E2E 0.2.86)
- ~~초대 코드 사용자 문구 최소 공개~~ (0.2.82 — [67-access-gate.md](67-access-gate.md))
- ~~ASR_ADMIN_EMAILS ops · 하드코딩 기본값 제거~~ (0.2.82 — [67-access-gate.md](67-access-gate.md))
- ~~초대 redeem E2E · Settings 로그아웃 OTP 잔여 제거~~ (0.2.83 — [67-access-gate.md](67-access-gate.md))
- ~~모바일 셸 · 로그인 게이트 · 탭 3개~~ (0.2.84 — [68-mobile-shell-nav.md](68-mobile-shell-nav.md))
- ~~액세스 게이트 GCS 공유 진실~~ (0.2.86 — [69-access-gate-gcs.md](69-access-gate-gcs.md); Cloud Run 다 인스턴스)
- ~~실기 사이드로드 APK pin (0.2.86)~~ ([48-flutter-android-platform.md](48-flutter-android-platform.md); 폰 `versionName` = live API)
- ~~모바일 단일 PDF 업로드 (클라우드)~~ (0.2.87 — [70-mobile-upload.md](70-mobile-upload.md))
- ~~이어올리기 · GCS job 재접속~~ (0.2.88 — [71-mobile-upload-resume.md](71-mobile-upload-resume.md))
- ~~조각 업로드 · prefix 무결성 이어보내기~~ (0.2.89 — [72-chunked-upload.md](72-chunked-upload.md))
- ~~업로드·ingest 호출 횟수 한도~~ (0.2.91 — [73-ingest-rate-limit.md](73-ingest-rate-limit.md); 횟수만 · daily/용량 한도 없음)
- ~~백그라운드 업로드 알림 · FG · 완료 탭 열기~~ (0.2.91 — [74-bg-upload-notify.md](74-bg-upload-notify.md); ASR_MOBILE_UPLOAD_BACKGROUND)
- **Android Flutter MVP** — 남은 실기 완성도 ([33-mobile-flutter.md](33-mobile-flutter.md); 업로드·게이트 이후)

### 구현됨 (참고)

- OCR 스캔본 → **적응형 Gemini vision** ([14-vision-ocr-router.md](14-vision-ocr-router.md), `rich-v3`)

## 한 줄 규칙

새 기능을 넣을 때 **어느 M에 속하는지** PR/커밋 메시지에 적는다. M 밖이면 설계 문서부터 수정.
