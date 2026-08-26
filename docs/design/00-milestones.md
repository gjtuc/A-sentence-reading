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
- ~~업로드·ingest 호출 횟수 한도~~ (0.3.3 — [73-ingest-rate-limit.md](73-ingest-rate-limit.md); 횟수만 · daily/용량 한도 없음)
- ~~백그라운드 업로드 알림 · FG · 완료 탭 열기~~ (0.3.3 — [74-bg-upload-notify.md](74-bg-upload-notify.md); ASR_MOBILE_UPLOAD_BACKGROUND)
- ~~전화·OEM 중단 후 업로드 자동 재개~~ (0.3.3 — [75-upload-interrupt-resume.md](75-upload-interrupt-resume.md); approach A · ASR_MOBILE_UPLOAD_INTERRUPT_RESUME)
- ~~프로세스 종료 후 WorkManager 이어올리기~~ (0.3.3 · [76-upload-workmanager.md](76-upload-workmanager.md); ASR_MOBILE_UPLOAD_WORKMANAGER)
- ~~이메일 매직링크 로그인 · 앱 딥링크~~ (0.3.3 · [77-email-magic-link.md](77-email-magic-link.md); ASR_EMAIL_MAGIC_LINK · OTP 게이트 유지)
- ~~이메일 비밀번호 가입/로그인 제거 · OAuth+매직링크~~ (0.3.3 · [78-no-email-password-signup.md](78-no-email-password-signup.md))
- ~~쉐도잉 연습 옵트인(킬·설정 토글)~~ (0.3.3 · [79-shadowing-opt-in.md](79-shadowing-opt-in.md); ASR_SHADOWING_PRACTICE)
- ~~쉐도잉 청크 계획(유저별·ingest/백필)~~ (0.3.3 · [80-shadowing-chunks.md](80-shadowing-chunks.md); ASR_SHADOWING_PRACTICE)
- ~~헤더 ⋯ 메뉴 overflow · Cloud Run 쉐도잉 킬 변수~~ (0.3.3 · [81-header-more-overflow.md](81-header-more-overflow.md))
- ~~쉐도잉 연습 모드(루프·유저별 takes)~~ (0.3.3 · [82-shadowing-practice-loop.md](82-shadowing-practice-loop.md))
- ~~로그인 강제 게이트(웹·API·앱)~~ (0.3.3 · [83-login-required-gate.md](83-login-required-gate.md); ASR_LOGIN_REQUIRED)
- ~~로그인 후 초대 대기 전용 셸~~ (0.3.3 · [84-access-waiting-ux.md](84-access-waiting-ux.md))
- ~~웹 이메일 매직링크만 (비밀번호 UI 제거)~~ (0.3.3 · [85-web-magic-link-only.md](85-web-magic-link-only.md); ASR_EMAIL_MAGIC_LINK)
- ~~라이브 SMTP 배선 (status · CD)~~ (0.3.3 · [86-live-smtp-wiring.md](86-live-smtp-wiring.md); ASR_SMTP_*)
- ~~실기 APK pin · 매직→대기→초대 redeem~~ (0.3.3 · [87-device-apk-magic-invite-e2e.md](87-device-apk-magic-invite-e2e.md))
- ~~웹·앱 첨자 표시 · TTS 손질~~ (0.3.4 · [88-rich-display-tts-polish.md](88-rich-display-tts-polish.md))
- ~~실기 보관 논문 첨자·TTS E2E~~ (0.3.4 · [89-device-rich-display-e2e.md](89-device-rich-display-e2e.md))
- ~~TTS 단위 사전 (Wh/L · SI energy)~~ (0.3.5 · [90-tts-unit-lexicon.md](90-tts-unit-lexicon.md))
- ~~실기 Wh/L TTS 청취~~ (0.3.5 · [91-device-tts-unit-lexicon-e2e.md](91-device-tts-unit-lexicon-e2e.md))
- ~~그림·표 캡션 번호 순 · graphical abstract~~ (0.3.6 · [92-figure-caption-order.md](92-figure-caption-order.md); rich-v8)
- ~~앱 Live Enable/IPS 푸터 제거~~ (0.3.7 · [93-remove-live-enable-footer.md](93-remove-live-enable-footer.md))
- ~~그림 줌 프레임 전체 사용~~ (0.3.8 · [94-figure-zoom-fill-frame.md](94-figure-zoom-fill-frame.md))
- ~~문장·그림 스와이프 이전/다음~~ (0.3.9 · [95-reader-swipe-nav.md](95-reader-swipe-nav.md))
- ~~TTS 배속 → 설정 탭~~ (0.3.10 · [96-tts-settings-tab.md](96-tts-settings-tab.md))
- ~~문장/그림 더블탭 전체 화면~~ (0.3.11 · [97-reader-panel-expand.md](97-reader-panel-expand.md))
- ~~분할 바 드래그 · 자석 · 엣지 스냅~~ (0.3.12 · [98-reader-split-drag.md](98-reader-split-drag.md))
- ~~모바일 번역 설정 옵트인(ingest/open 게이트)~~ (0.3.13 · [99-mobile-translate-opt-in.md](99-mobile-translate-opt-in.md))
- ~~읽기 프레임 헤더 탭 토글~~ (0.3.14 · [100-reader-chrome-toggle.md](100-reader-chrome-toggle.md))
- ~~보관 목록 길게 눌러 순서 변경~~ (0.3.15 · [101-library-reorder.md](101-library-reorder.md))
- ~~보관 삭제(휴지통) · GCS·사용자 기록 정리~~ (0.3.16 · [102-library-delete.md](102-library-delete.md))
- ~~모바일 TTS 목소리·랜덤 난이도 (읽기·연습)~~ (0.3.17 · [103-mobile-tts-voice-random.md](103-mobile-tts-voice-random.md))
- ~~설정 초대 코드: 승인·관리자 숨김 · Deny 재입력~~ (0.3.18 · [104-hide-settings-invite-when-allowed.md](104-hide-settings-invite-when-allowed.md))
- ~~업로드 실패 알림 · 처리 폴링 20분~~ (0.3.19 · [105-upload-fail-notify.md](105-upload-fail-notify.md))
- ~~품질 단계 Gemini 타임아웃 · GCS 진행률~~ (0.3.20 · [106-ingest-quality-timeout.md](106-ingest-quality-timeout.md))
- ~~Cloud Run ingest job lease·재시작~~ (0.3.21 · [107-ingest-job-reclaim.md](107-ingest-job-reclaim.md))
- ~~보관 cache 없이 완료 금지~~ (0.3.22 · [108-fail-closed-no-cache.md](108-fail-closed-no-cache.md))
- ~~보관함 인제스트 에러 닫기 · terminal 초안 정리~~ (0.3.23 · [109-dismiss-library-ingest-error.md](109-dismiss-library-ingest-error.md))
- ~~ingest checkpoint 봉투 · TTL/버전 폐기~~ (0.3.24 · [110-ingest-checkpoint-envelope.md](110-ingest-checkpoint-envelope.md))
- ~~want_chunks NameError 복구 · open JSON 실패~~ (0.3.25 · [111-fix-want-chunks-nameerror.md](111-fix-want-chunks-nameerror.md))
- ~~ingest mid-stage resume skip (payload)~~ (0.3.26 · [112-ingest-resume-skip.md](112-ingest-resume-skip.md))
- ~~shadowing chunk build 시간 예산·이어하기 (504 회피)~~ (0.3.27 · [113-shadowing-chunk-budget.md](113-shadowing-chunk-budget.md))
- ~~보관 열기 빈 세션 거절 · GCS 재pull~~ (0.3.28 · [114-library-open-empty-session.md](114-library-open-empty-session.md))
- ~~읽기 패널 clipBehavior null 크래시~~ (0.3.29 · [115-reader-clip-without-decoration.md](115-reader-clip-without-decoration.md))
- ~~그림 핀치 vs 스와이프 제스처 충돌 완화~~ (0.3.30 · [116-figure-pinch-vs-swipe.md](116-figure-pinch-vs-swipe.md))
- ~~그림 넘기기 = 한 손가락만~~ (0.3.31 · [117-figure-swipe-one-finger.md](117-figure-swipe-one-finger.md))
- ~~그림 핀치 줌 민감도 (확실히 체감)~~ (0.3.32 · [118-figure-pinch-sensitivity.md](118-figure-pinch-sensitivity.md))
- ~~shadowing chunks/build fail-closed · pending 이어받기~~ (0.3.33 · [119-shadowing-chunks-build-failclosed.md](119-shadowing-chunks-build-failclosed.md))
- ~~쉐도잉 「다시」(말하기만) · 「다시 듣기」(내 녹음)~~ (0.3.34 · [120-shadowing-retry-replay.md](120-shadowing-retry-replay.md))
- ~~보관 열기 GCS-first · pull 실패 시 로컬 폴백 금지~~ (0.3.35 · [121-library-open-gcs-first.md](121-library-open-gcs-first.md))
- ~~보관 드래그 흰 섬광 제거~~ (0.3.36 · [122-library-reorder-no-white-flash.md](122-library-reorder-no-white-flash.md))
- ~~진행 복원: 문장+그림 정밀 · fail-closed~~ (0.3.37 · [123-progress-restore-precise.md](123-progress-restore-precise.md))
- ~~빠진 그림: 정직한 빈 슬롯 · 앱 Fig. 점프~~ (0.3.38 · [124-missing-figures.md](124-missing-figures.md))
- ~~캡션 우선 그림 추출 (Fig/Table/Scheme)~~ (0.3.39 · [125-caption-anchored-figures.md](125-caption-anchored-figures.md))
- ~~소프트 캡션 라벨 (구두점 없이 Fig/Table/Scheme)~~ (0.3.40 · [126-soft-caption-labels.md](126-soft-caption-labels.md))
- ~~캡션 단어 이어붙이기 (Elsevier 줄바꿈)~~ (0.3.41 · [127-caption-word-join.md](127-caption-word-join.md))
- ~~표/그림 단 폭 클립 (잘림 완화)~~ (0.3.42 · [128-clip-column-width.md](128-clip-column-width.md))
- ~~문장 먼저 열기 · 그림 ±1 창~~ (0.3.45 · [129-lazy-figure-open.md](129-lazy-figure-open.md))
- ~~클라우드 오류 로그 · 관리자 배지~~ (0.3.46 · [130-cloud-error-logs.md](130-cloud-error-logs.md))
- ~~캡션 전문 표시 · normalize 상한~~ (0.3.47 · [131-caption-full-text.md](131-caption-full-text.md))
- ~~업로드·정제 중 취소 (조기 discard · ready+ 거절)~~ (0.3.48 · [132-ingest-cancel.md](132-ingest-cancel.md))
- ~~로그아웃·계정전환 시 로컬 세션/보관함/draft 격리~~ (0.3.49 · [133-logout-session-isolation.md](133-logout-session-isolation.md))
- ~~업로드·정제 진전 없음 hang (로컬 실패 + 오류 로그)~~ (0.3.50 · [134-ingest-upload-hang.md](134-ingest-upload-hang.md))
- ~~모바일 Google Custom Tab GIS (SHA-1 sideload 우회)~~ (0.3.51 · [65-mobile-oauth.md](65-mobile-oauth.md))
- ~~표지(제목 페이지) → 그림 캐러셀 1번~~ (0.3.53 · [135-cover-as-figure.md](135-cover-as-figure.md))
- ~~옆 논문 페이지 제거 (첫 논문만 · 경계 실패 시 거절)~~ (0.3.54 · [136-strip-adjacent-articles.md](136-strip-adjacent-articles.md))
- ~~캡션 덩어리 쪼개기 (다중 라벨 분리 · fail-closed)~~ (0.3.55 · [137-split-caption-lumps.md](137-split-caption-lumps.md))
- ~~로컬 서버 흔적 제거 (Live+폰만)~~ (0.3.56 · [138-no-local-server-traces.md](138-no-local-server-traces.md))
- ~~Fig. 점프 칩 정식화 (앱+웹 · 문장 아래)~~ (0.3.57 · [139-fig-ref-chip-formal.md](139-fig-ref-chip-formal.md))
- ~~Flutter MVP 백로그 쪼개기~~ (docs · [140-mobile-mvp-backlog-split.md](140-mobile-mvp-backlog-split.md); ~~[141-mobile-sentence-notes.md](141-mobile-sentence-notes.md)~~ 취소)
- ~~키보드 문장 노트 제거 (웹 끔 · 녹음 연습 유지)~~ (0.3.58 · [142-no-keyboard-sentence-notes.md](142-no-keyboard-sentence-notes.md))
- ~~스와이프 방향 관례 정정 (왼쪽=다음 · 오른쪽=이전)~~ (0.3.59 · [143-swipe-direction-flip.md](143-swipe-direction-flip.md))
- ~~보관 TTL 90일 · ⚠️ 경고 · +90일 연장 · 읽는 중 grace~~ (0.3.60 · [144-paper-retention-ttl.md](144-paper-retention-ttl.md))
- ~~보관 재분석 앱 UI (원본 → job 폴링 · 설정 번역 연동)~~ (0.3.61 · [145-mobile-library-reanalyze.md](145-mobile-library-reanalyze.md))
- ~~보관 연장 +90일 (14→90)~~ (0.3.62 · [144-paper-retention-ttl.md](144-paper-retention-ttl.md))
- **다음 구현:** 계정 연결 앱 UI (140 목록 · [23](23-multi-auth-link.md))

### 구현됨 (참고)

- OCR 스캔본 → **적응형 Gemini vision** ([14-vision-ocr-router.md](14-vision-ocr-router.md), `rich-v3`)

## 한 줄 규칙

새 기능을 넣을 때 **어느 M에 속하는지** PR/커밋 메시지에 적는다. M 밖이면 설계 문서부터 수정.
