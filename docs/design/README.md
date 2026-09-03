# Design index — 구현용 쪼개진 설계

상위 제품·UX는 [PRODUCT.md](../PRODUCT.md) · [UX.md](../UX.md) · [ARCHITECTURE.md](../ARCHITECTURE.md).  
아래는 **코드를 쓰기 직전에 필요한 계약·알고리즘·상태·한계**다.

| # | 문서 | 채운 빈틈 |
|---|------|-----------|
| 00 | [00-milestones.md](00-milestones.md) | 무엇을 언제 구현할지 · 합격 기준 |
| 01 | [01-data-model.md](01-data-model.md) | 필드·ID·직렬화·불변조건 디테일 |
| 02 | [02-pdf-extract.md](02-pdf-extract.md) | PyMuPDF 전략·그림 필터·다단·실패 |
| 03 | [03-sentence-split.md](03-sentence-split.md) | 경계 규칙·약어·픽스처 |
| 04 | [04-api-contract.md](04-api-contract.md) | HTTP 스키마·에러 코드 |
| 05 | [05-session-store.md](05-session-store.md) | 세션 수명·디스크 레이아웃 |
| 06 | [06-ui-states.md](06-ui-states.md) | UI 상태머신·빈/로딩/에러 |
| 07 | [07-typography-tokens.md](07-typography-tokens.md) | CSS 토큰 수치·변경 규칙 |
| 08 | [08-errors.md](08-errors.md) | 에러 분류·사용자 메시지 |
| 09 | [09-testing.md](09-testing.md) | 단위/계약 테스트·픽스처 |
| 10 | [10-security-limits.md](10-security-limits.md) | 업로드·경로·리소스 한도 |
| 11 | [11-figure-collapse.md](11-figure-collapse.md) | 스플리터 드래그로 그림 접기·문장 상단화 |
| 12 | [12-gemini-debone.md](12-gemini-debone.md) | Gemini로 저자·인용 가시 제거 · Title/Abstract/Body |
| 13 | [13-rich-text-two-pass.md](13-rich-text-two-pass.md) | 전역 survey + 청크 debone · sub/sup/이탤릭 HTML |
| 14 | [14-vision-ocr-router.md](14-vision-ocr-router.md) | PyMuPDF 품질 판정 + 선택적 Gemini vision OCR |
| 15 | [15-tts-and-gestures.md](15-tts-and-gestures.md) | Cloud TTS · 접기 제스처 제거 · 크롭 유지 |
| 16 | [16-sentence-notes.md](16-sentence-notes.md) | 문장별 성찰 노트 · Enter×3 닫기 · localStorage |
| 17 | [17-rumination-revisions.md](17-rumination-revisions.md) | append-only 리비전 · 섹션 분기 리뷰 |
| 18 | [18-paper-library.md](18-paper-library.md) | 보관 목록 UI · cache open |
| 19 | [19-pipeline-cache.md](19-pipeline-cache.md) | stale 보관본 정책 · 재분석 |
| 20 | [20-source-backup.md](20-source-backup.md) | 원본 PDF/DOCX 백업 · 재분석 |
| 21 | [21-progress-restore.md](21-progress-restore.md) | 문장·그림 진행 localStorage |
| 22 | [22-google-auth-gcs.md](22-google-auth-gcs.md) | Google 로그인 · UID별 GCS 칸 |
| 23 | [23-multi-auth-link.md](23-multi-auth-link.md) | 카카오·이메일 · 계정 연결 |
| 24 | [24-gcs-bucket-enable.md](24-gcs-bucket-enable.md) | GCS 버킷 실연결 (운영) |
| 25 | [25-cloud-run.md](25-cloud-run.md) | Cloud Run 문지기 (PC 꺼도) |
| 26 | [26-cloud-run-oauth-origin.md](26-cloud-run-oauth-origin.md) | Run URL · Google OAuth 원본 |
| 27 | [27-usage-metering.md](27-usage-metering.md) | 유저별 사용량 · 추정 비용 |
| 28 | [28-fig-ref-jump.md](28-fig-ref-jump.md) | Fig. N → 그림 점프 칩 |
| 29 | [29-compound-figures.md](29-compound-figures.md) | 복합 그림 1a/1b · rich-v4 |
| 30 | (삭제) | 음절 보조 — **하지 않음** · 0.2.30 원복 |
| 31 | [31-reading-order.md](31-reading-order.md) | 다단 좌→우 순서 · 기하+vision |
| 32 | [32-github-cd.md](32-github-cd.md) | GitHub CI · Cloud Run CD 게이트 |
| 33 | [33-mobile-flutter.md](33-mobile-flutter.md) | Android Flutter 「문장 읽기」 · API 재사용 · APK |
| 34 | [34-tab-close.md](34-tab-close.md) | 논문 탭 × 닫기 · 탭 범위 저장 |
| 35 | [35-translate-simple.md](35-translate-simple.md) | 영→한 단순 번역 · on/off |
| 36 | [36-translate-pipeline.md](36-translate-pipeline.md) | draft→sense→polish |
| 37 | [37-stt-browser.md](37-stt-browser.md) | 브라우저 STT · 단어 diff |
| 38 | [38-stt-server.md](38-stt-server.md) | 서버 STT · MediaRecorder |
| 39 | [39-translate-side-by-side.md](39-translate-side-by-side.md) | EN\|KO 좌우 동형 |
| 40 | [40-ingest-section-translate.md](40-ingest-section-translate.md) | ingest 섹션 번역 · 요지 · 캡션 |
| 41 | [41-cite-ref-open.md](41-cite-ref-open.md) | 각주 → References → DOI/Crossref |
| 42 | [42-translate-ingest-only.md](42-translate-ingest-only.md) | live 번역 제거 · 보관본 백필 |
| 58 | [58-header-overflow.md](58-header-overflow.md) | 헤더 파일 열기 + `⋯` · Live Enable/IPS 밖 |
| 59 | [59-guide-header.md](59-guide-header.md) | Guide 밖/`⋯` 안 · 안내 dialog |
| 60 | [60-panel-hints.md](60-panel-hints.md) | 패널 단축키 줄 기본 숨김 · Guide 옵션 |
| 61 | [61-mobile-email-auth.md](61-mobile-email-auth.md) | Flutter 이메일 로그인 · asr_session |
| 62 | [62-mobile-library.md](62-mobile-library.md) | Flutter 보관 목록 · open |
| 63 | [63-mobile-reader.md](63-mobile-reader.md) | Flutter reader independent cursors |
| 64 | [64-mobile-tts.md](64-mobile-tts.md) | Flutter TTS · POST /api/tts 재생 |
| 65 | [65-mobile-oauth.md](65-mobile-oauth.md) | Flutter Google·카카오 OAuth |
| 66 | [66-mobile-theme.md](66-mobile-theme.md) | Flutter 테마 system/light/dark |
| 67 | [67-access-gate.md](67-access-gate.md) | OTP 초대 코드 · admin allow/deny |
| 68 | [68-mobile-shell-nav.md](68-mobile-shell-nav.md) | 로그인 게이트 · 탭 3개 · 설정에 계정/서버 |
| 69 | [69-access-gate-gcs.md](69-access-gate-gcs.md) | 액세스 게이트 초대·이벤트·redeem → GCS 공유 |
| 70 | [70-mobile-upload.md](70-mobile-upload.md) | Flutter 단일 PDF 업로드 · 클라우드 |
| 71 | [71-mobile-upload-resume.md](71-mobile-upload-resume.md) | 이어올리기 · GCS job · 앱 재접속 |
| 72 | [72-chunked-upload.md](72-chunked-upload.md) | 조각 업로드 · prefix 무결성 이어보내기 |
| 73 | [73-ingest-rate-limit.md](73-ingest-rate-limit.md) | 업로드·ingest 호출 횟수 한도 |
| 74 | [74-bg-upload-notify.md](74-bg-upload-notify.md) | 백그라운드 업로드 알림 · FG · 완료 탭 열기 |
| 75 | [75-upload-interrupt-resume.md](75-upload-interrupt-resume.md) | 전화·중단 후 업로드 자동 재개 |
| 76 | [76-upload-workmanager.md](76-upload-workmanager.md) | 프로세스 종료 후 WorkManager 이어올리기 |
| 77 | [77-email-magic-link.md](77-email-magic-link.md) | 이메일 매직링크 로그인 · 앱 딥링크 |
| 78 | [78-no-email-password-signup.md](78-no-email-password-signup.md) | 이메일 비밀번호 가입/로그인 제거 · OAuth+매직링크 |
| 79 | [79-shadowing-opt-in.md](79-shadowing-opt-in.md) | 쉐도잉 연습 옵트인 · 킬·설정 토글 |
| 80 | [80-shadowing-chunks.md](80-shadowing-chunks.md) | 쉐도잉 청크 계획 · 유저별 ingest/백필 |
| 81 | [81-header-more-overflow.md](81-header-more-overflow.md) | 헤더 ⋯ overflow · CD 쉐도잉 킬 |
| 82 | [82-shadowing-practice-loop.md](82-shadowing-practice-loop.md) | 쉐도잉 연습 모드 · 루프·takes |
| 83 | [83-login-required-gate.md](83-login-required-gate.md) | 로그인 강제 게이트 · 웹·API·앱 |
| 84 | [84-access-waiting-ux.md](84-access-waiting-ux.md) | 로그인 후 초대 대기 전용 셸 |
| 85 | [85-web-magic-link-only.md](85-web-magic-link-only.md) | 웹 이메일 매직링크만 · 비밀번호 UI 제거 |
| 86 | [86-live-smtp-wiring.md](86-live-smtp-wiring.md) | 라이브 SMTP 배선 · status · CD 전달 |
| 87 | [87-device-apk-magic-invite-e2e.md](87-device-apk-magic-invite-e2e.md) | 실기 APK 0.3.3 · 매직→대기→초대 입력 |
| 88 | [88-rich-display-tts-polish.md](88-rich-display-tts-polish.md) | 웹·앱 첨자 표시 · TTS 단위 손질 |
| 89 | [89-device-rich-display-e2e.md](89-device-rich-display-e2e.md) | 실기 보관 논문 · 첨자 표시+TTS E2E |
| 90 | [90-tts-unit-lexicon.md](90-tts-unit-lexicon.md) | TTS 단위 사전 · Wh/L≠텅스텐 |
| 91 | [91-device-tts-unit-lexicon-e2e.md](91-device-tts-unit-lexicon-e2e.md) | 실기 Wh/L TTS 청취 확인 |
| 92 | [92-figure-caption-order.md](92-figure-caption-order.md) | 그림·표 캡션 번호 순 · GA 예외 |
| 93 | [93-remove-live-enable-footer.md](93-remove-live-enable-footer.md) | 앱 Live Enable/IPS 푸터 제거 |
| 94 | [94-figure-zoom-fill-frame.md](94-figure-zoom-fill-frame.md) | 그림 줌이 프레임 전체 사용 |
| 95 | [95-reader-swipe-nav.md](95-reader-swipe-nav.md) | 문장·그림 가로 스와이프 이전/다음 |
| 96 | [96-tts-settings-tab.md](96-tts-settings-tab.md) | TTS 배속을 설정 탭으로 |
| 97 | [97-reader-panel-expand.md](97-reader-panel-expand.md) | 문장/그림 더블탭 전체 화면 |
| 98 | [98-reader-split-drag.md](98-reader-split-drag.md) | 분할 바 드래그 · 자석 · 엣지 스냅 |
| 99 | [99-mobile-translate-opt-in.md](99-mobile-translate-opt-in.md) | 모바일 번역 설정 옵트인 |
| 100 | [100-reader-chrome-toggle.md](100-reader-chrome-toggle.md) | 읽기 프레임 헤더 탭 토글 |
| 101 | [101-library-reorder.md](101-library-reorder.md) | 보관 목록 드래그 순서 |
| 102 | [102-library-delete.md](102-library-delete.md) | 보관 휴지통 삭제 · 기록 정리 |
| 103 | [103-mobile-tts-voice-random.md](103-mobile-tts-voice-random.md) | 모바일 TTS 목소리·랜덤 난이도 |
| 104 | [104-hide-settings-invite-when-allowed.md](104-hide-settings-invite-when-allowed.md) | 설정 초대 코드 승인·관리자 숨김 |
| 105 | [105-upload-fail-notify.md](105-upload-fail-notify.md) | 업로드 실패 알림 · 폴링 20분 |
| 106 | [106-ingest-quality-timeout.md](106-ingest-quality-timeout.md) | 품질 단계 Gemini 타임아웃 · GCS 진행률 |
| 107 | [107-ingest-job-reclaim.md](107-ingest-job-reclaim.md) | Cloud Run 인스턴스 간 ingest job 재개 |
| 108 | [108-fail-closed-no-cache.md](108-fail-closed-no-cache.md) | 보관 cache 없이 완료 금지 |
| 109 | [109-dismiss-library-ingest-error.md](109-dismiss-library-ingest-error.md) | 보관함 인제스트 에러 닫기 · terminal 초안 정리 |
| 110 | [110-ingest-checkpoint-envelope.md](110-ingest-checkpoint-envelope.md) | ingest checkpoint 봉투 · reclaim 수락/폐기 |
| 111 | [111-fix-want-chunks-nameerror.md](111-fix-want-chunks-nameerror.md) | want_chunks NameError 복구 · open JSON 실패 |
| 112 | [112-ingest-resume-skip.md](112-ingest-resume-skip.md) | ingest mid-stage resume skip (payload 소비) |
| 113 | [113-shadowing-chunk-budget.md](113-shadowing-chunk-budget.md) | shadowing chunk build 시간 예산·이어하기 |
| 114 | [114-library-open-empty-session.md](114-library-open-empty-session.md) | 보관 열기 빈 세션 거절 · GCS 재pull |
| 115 | [115-reader-clip-without-decoration.md](115-reader-clip-without-decoration.md) | 읽기 패널 clipBehavior null crash · ClipRect |
| 116 | [116-figure-pinch-vs-swipe.md](116-figure-pinch-vs-swipe.md) | 그림 핀치 vs 스와이프 제스처 충돌 완화 |
| 117 | [117-figure-swipe-one-finger.md](117-figure-swipe-one-finger.md) | 그림 넘기기 = 한 손가락만 |
| 118 | [118-figure-pinch-sensitivity.md](118-figure-pinch-sensitivity.md) | 그림 핀치 줌 민감도 (확실히 체감) |
| 119 | [119-shadowing-chunks-build-failclosed.md](119-shadowing-chunks-build-failclosed.md) | shadowing chunks/build 500·pending 이어받기 |
| 120 | [120-shadowing-retry-replay.md](120-shadowing-retry-replay.md) | 쉐도잉 「다시」·「다시 듣기」 |
| 121 | [121-library-open-gcs-first.md](121-library-open-gcs-first.md) | 보관 열기 GCS-first · pull 실패 시 로컬 금지 |
| 122 | [122-library-reorder-no-white-flash.md](122-library-reorder-no-white-flash.md) | 보관 드래그 흰 섬광 제거 |
| 123 | [123-progress-restore-precise.md](123-progress-restore-precise.md) | 진행 복원 문장+그림 정밀 · fail-closed |
| 124 | [124-missing-figures.md](124-missing-figures.md) | 빠진 그림 정직한 빈 슬롯 · 앱 Fig. 점프 |
| 125 | [125-caption-anchored-figures.md](125-caption-anchored-figures.md) | 캡션 우선 Fig/Table/Scheme 추출 |
| 126 | [126-soft-caption-labels.md](126-soft-caption-labels.md) | 소프트 캡션 라벨 |
| 127 | [127-caption-word-join.md](127-caption-word-join.md) | Elsevier 단어 줄바꿈 캡션 이어붙이기 |
| 128 | [128-clip-column-width.md](128-clip-column-width.md) | 표/그림 단 폭 클립 |
| 129 | [129-lazy-figure-open.md](129-lazy-figure-open.md) | 문장 먼저 열기 · 그림 ±1 창 |
| 130 | [130-cloud-error-logs.md](130-cloud-error-logs.md) | 오류 탐지 · 클라우드 로그 · 관리자 배지 |
| 131 | [131-caption-full-text.md](131-caption-full-text.md) | 캡션 전문(줄바꿈·스크롤) · normalize 상한 |
| 132 | [132-ingest-cancel.md](132-ingest-cancel.md) | 업로드·정제 중 취소 (조기 discard · ready+ 거절) |
| 133 | [133-logout-session-isolation.md](133-logout-session-isolation.md) | 로그아웃·계정전환 로컬 세션/보관함 격리 |
| 134 | [134-ingest-upload-hang.md](134-ingest-upload-hang.md) | 업로드·정제 진전 없음 hang · 오류 로그 |
| 135 | [135-cover-as-figure.md](135-cover-as-figure.md) | 표지(제목 페이지) → 그림 캐러셀 1번 |
| 136 | [136-strip-adjacent-articles.md](136-strip-adjacent-articles.md) | 옆 논문 페이지 제거 (첫 논문만) |
| 137 | [137-split-caption-lumps.md](137-split-caption-lumps.md) | 캡션 덩어리 쪼개기 (다중 라벨 분리) |
| 138 | [138-no-local-server-traces.md](138-no-local-server-traces.md) | 로컬 서버 흔적 제거 (Live+폰만) |
| 139 | [139-fig-ref-chip-formal.md](139-fig-ref-chip-formal.md) | Fig. 점프 칩 정식화 (앱+웹 · 문장 아래) |
| 140 | [140-mobile-mvp-backlog-split.md](140-mobile-mvp-backlog-split.md) | Flutter MVP 백로그 쪼개기 (33) |
| 141 | [141-mobile-sentence-notes.md](141-mobile-sentence-notes.md) | ~~모바일 문장 노트~~ (**취소**) |
| 142 | [142-no-keyboard-sentence-notes.md](142-no-keyboard-sentence-notes.md) | 키보드 문장 노트 제거 (녹음 연습 유지) |
| 143 | [143-swipe-direction-flip.md](143-swipe-direction-flip.md) | 스와이프 방향 관례 정정 (왼쪽=다음) |
| 144 | [144-paper-retention-ttl.md](144-paper-retention-ttl.md) | 보관 TTL · ⚠️ · 연장 · purge |
| 145 | [145-mobile-library-reanalyze.md](145-mobile-library-reanalyze.md) | 보관 재분석 앱 UI |
| 146a | [146a-mobile-account-link.md](146a-mobile-account-link.md) | 앱 계정 연결/해제 (Settings) |
| 146c | [146c-mobile-kakao-oauth-scheme.md](146c-mobile-kakao-oauth-scheme.md) | 카카오 OAuth scheme (flutter_web_auth_2) |
| 146b | [146b-account-warehouse-merge.md](146b-account-warehouse-merge.md) | 계정 창고 병합 (**후보**) |
| 160 | [160-mobile-library-reader-polish.md](160-mobile-library-reader-polish.md) | 보관 메타 · Title Page · shadowing GCS · 북마크 배지 |
| 161 | [161-mobile-apk-download.md](161-mobile-apk-download.md) | 설정 APK 다운로드 |
| 162 | [162-practice-camera-mirror.md](162-practice-camera-mirror.md) | 연습 카메라 미러 · 만료 날짜 |
| 163 | [163-figure-layout-edit-v2.md](163-figure-layout-edit-v2.md) | Figure layout edit v2 · slot_plan · commit |
| 164 | [164-fig-ref-panel-fallback.md](164-fig-ref-panel-fallback.md) | Fig-ref 패널 폴백 |
| 166 | [166-reader-annotations.md](166-reader-annotations.md) | 모바일 주석 MVP · GCS sidecar · 하이라이트·메모 |
| 167 | [167-debone-quality-guards.md](167-debone-quality-guards.md) | debone 품질 가드 · warnings 영속 · Body 진단 |
| 168 | [168-ingest-observability.md](168-ingest-observability.md) | ingest·open·figures 과잉 계측 · phase · T1–T10 · [체크리스트](168-audit-checklist.md) |
| 169 | [169-agent-evidence-bus.md](169-agent-evidence-bus.md) | 전역 증거 버스 · UI 없음 · 에이전트 pull · [체크리스트](169-audit-checklist.md) |
| 169c | [169c-dense-translate-open-auth.md](169c-dense-translate-open-auth.md) | 번역·open·auth 촘촘 evidence (0.3.124) |
| 169d | [169d-full-product-evidence.md](169d-full-product-evidence.md) | 전 제품 P0/P1 evidence (0.3.125) |
| 169e | [169e-google-batch-evidence.md](169e-google-batch-evidence.md) | Google batch/chunk call evidence (0.3.126) |
| 169g | [169g-causal-handoff-evidence.md](169g-causal-handoff-evidence.md) | 인과 handoff 설계 + evidence floor 가드 (7d retention 목표) |
| 169h | [169h-interior-checkpoint-evidence.md](169h-interior-checkpoint-evidence.md) | 단계 **안쪽** checkpoint / `blocked_on` densify (title→next 스톨) |
| 169i | [169i-artifact-transfer-ledger.md](169i-artifact-transfer-ledger.md) | 조각 source→sink 장부 (hash·locator·transfer; **0.3.134** I0–I2) |
| 169j | [169j-translate-on-item-off-critical-path.md](169j-translate-on-item-off-critical-path.md) | 번역 `on_item` cold path 분리 · writer/DropOldest (**0.3.135**) |
| 169k | [169k-observability-pull-verdicts.md](169k-observability-pull-verdicts.md) | pull/track verdict 규칙 · I3 figure · I4/K3–K4 로드맵 |
| 169o | [169o-harmonize-residual.md](169o-harmonize-residual.md) | ingest 후 harmonize residual · 배너 honesty |
| 169p | [169p-shadowing-practice-evidence.md](169p-shadowing-practice-evidence.md) | 쉐도잉 prep 증거·verdict (제품 수정 전) |
| 171 | [171-device-figure-cache.md](171-device-figure-cache.md) | 폰 그림·표 영구 캐시 · 삭제 시 purge |
| 172 | [172-access-sticky-on-timeout.md](172-access-sticky-on-timeout.md) | access/status 타임아웃 시 sticky unlock · 승인대기 튕김 방지 |

**구현 순서 (강제):** 00 → 01 → 04/05 뼈대 → 02 → 03 → 06/07 UI 연결 → 08/09/10 보강.  
스플리터(11)는 UI 스켈레톤과 함께 구현 가능 (PDF와 무관).  
13은 12 위에 이어서 구현.  
14는 PDF ingest에서 12/13 직전(텍스트 복구)에 붙는다.  
15는 UI·TTS (레이아웃 접기보다 크롭·읽기 우선; 배속은 Signalsmith vendored + 폴백).  
16은 UI만 (서버 없음 · TTS Enter와 충돌 주의).  
17은 16 위에 리비전·분기 리뷰 (TTS·노트·voice·논문캐시 GCS 0.2.12 — 원본 PDF는 미동기).  
18은 17 캐시 위에 보관 목록·즉시 열기·목록 삭제 (0.2.14).  
19는 stale `pipeline_version` 표시·ingest 재분석·open 허용 (0.2.15).  
20은 원본 PDF/DOCX 백업·GCS sync·보관 「재분석」 (0.2.16).  
21은 M5 진행 복원 — `asr.progress.v1` · `content_hash` (0.2.17).  
22는 Google 로그인 · `users/{uid}/` GCS 칸 (0.2.18).  
23은 카카오·이메일 로그인 + 계정 연결 (0.2.19).  
24는 GCS 버킷 실연결 (0.2.20).  
25는 Cloud Run 문지기 (0.2.21–0.2.22 배포).  
26은 Run URL Google OAuth 원본 + 로컬 「클라우드」링크 (0.2.23).  
27은 유저별 사용량·추정 비용 (0.2.24 · **관리자 전용 UI** 0.2.37).  
28은 Fig./Scheme/Table 참조 → 그림 점프 칩 (0.2.25).  
29는 compound figure 1a/1b 균등 분해 · `rich-v4` (0.2.26).  
31은 다단 읽는 순서 — 기하 재정렬 + vision 강제 (0.2.32 · `rich-v5`).  
그림 클립 zoom **8** · `rich-v6` (0.2.41).  
32는 GitHub pytest CI + Cloud Run CD (0.2.33–0.2.35 · Secrets 동기화·CD 켜짐).
33은 Android Flutter 앱 「문장 읽기」 — Cloud Run API 재사용 · APK 사이드로드 (문서; 구현 후속).  
34는 논문 탭 × 닫기 — 진행·노트 저장 후 탭만 닫기 (0.2.42).  
35는 영→한 단순 번역 + 표시 on/off (0.2.43) — 다단계 번역은 후속.  
36는 영→한 다단계 번역 draft→sense→polish (0.2.44) — 기본 pipeline · simple 호환.  
37는 브라우저 STT 발음 연습 — 원문 vs 인식 diff · 점수 없음 (0.2.45).  
38는 서버 STT — MediaRecorder 업로드 · Gemini 전사 · 브라우저 폴백 (0.2.46).  
39는 번역 표시 EN|KO 좌우 동형 — 전체·축소 공통 (0.2.47).  
40는 첨부 시 섹션 번역 + 요지 재감수 + 캡션 (0.2.48).  
41는 본문 각주 → References → DOI/Crossref 원문 열기 (0.2.49).  
42는 읽기 live 번역 제거 · 보관본 KO 백필 (0.2.50).
43는 섹션 번역 stage 진행 문구 세분화 (0.2.51).  
44는 compound 자동 분리 ingest 끊기 · rich-v7 (0.2.52).
45는 progressive 읽기 열기 · 단계 KO (0.2.53).
46는 섹션 번역 문장 병렬 · ASR_TRANSLATE_WORKERS (0.2.54).  
47는 Flutter `mobile/` 스캐폴드 · status 클라이언트 (0.2.55).  
48는 Flutter `android/` 플랫폼 · applicationId (0.2.56).  
49는 각주 표시 정리 · 박스 [n] 숨김 · FS 칩 hover (0.2.57).  
50는 한글 번역 어절 줄바꿈 · keep-all (0.2.58).  
51는 되새김질 이어 보기 · 한 박스 (0.2.59).
52는 되새김질 목소리 이어 듣기 (0.2.60).
53는 되새김질 on/off 옵션 (0.2.61).
54는 되새김질 일시 정지 클립 다시 듣기/재녹음 (0.2.62).
55는 되새김질 flow 콕 수정 (0.2.63).
56는 되새김질 키보드 패리티 (0.2.64).
57는 되새김질 흰 십자 (0.2.65).  
58는 헤더 「파일 열기」+ `⋯` overflow (0.2.66).  
59는 Guide 헤더 배치 · `⋯` 안 옵션 (0.2.67).  
60는 패널 단축키 안내 줄 기본 숨김 (0.2.68).
61는 Flutter 이메일 로그인·세션 (0.2.69).
62는 Flutter 보관 목록·open (0.2.70).
63는 Flutter 읽기·독립 커서 (0.2.71).
64는 Flutter TTS 현재 문장 재생 (0.2.72).
65는 Flutter Google·카카오 로그인 (0.2.73).
66는 Flutter 테마 3종 (0.2.74).
67는 액세스 게이트 OTP·Allow/Deny (0.2.82).  
68는 모바일 셸 · 로그인 게이트 · 탭 3개 (0.2.84).  
69는 액세스 게이트 GCS 공유 진실 (0.2.86).  
70는 Flutter 단일 PDF 업로드 · 클라우드 (0.2.87).  
71는 이어올리기 · GCS ingest job · 앱 재접속 (0.2.88).  
72는 조각 업로드 · prefix 무결성 이어보내기 (0.2.89).  
73는 업로드·ingest 호출 횟수 한도 (0.3.3).  
76은 프로세스 종료 후 WorkManager 이어올리기 (0.3.3).  
77은 이메일 매직링크 로그인 · 앱 딥링크 (0.3.3).
78은 이메일 비밀번호 가입/로그인 제거 (0.3.3).
79는 쉐도잉 연습 옵트인 킬·설정 토글 (0.3.3).
80 — 쉐도잉 청크 계획(유저별·ingest/백필) (0.3.3).
81 — 헤더 ⋯ overflow · CD 쉐도잉 킬 (0.3.3).
82 — 쉐도잉 연습 모드(루프·유저별 takes) (0.3.3).

음절(30)은 **하지 않음** (원복).
83은 로그인 강제 게이트(웹·API·앱) (0.3.3).
84은 로그인 후 초대 대기 전용 셸 (0.3.3).
87은 실기 APK 0.3.3 · 매직 딥링크 → 대기 → 초대 입력 (0.3.3).
88은 웹·앱 rich 첨자 표시 · TTS 단위·기호 손질 (0.3.4).
89은 실기 보관 논문에서 첨자 표시+TTS 확인 (0.3.4).
90은 TTS 단위 사전 · Wh/L → watt hour per liter (0.3.5).
91은 실기 Wh/L TTS 청취 확인 (0.3.5).
92는 그림·표 캡션 번호 순 정렬 · 초록 옆 GA (0.3.6 · rich-v8).
93은 앱 읽기/쉐도잉 Live Enable·IPS 푸터 제거 (0.3.7).
94는 그림 줌이 프레임 전체(검은 여백 포함)를 사용 (0.3.8).
95는 문장·그림 가로 스와이프 이전/다음 · 그림은 1×만 (0.3.9).
96은 TTS 배속을 설정 탭으로 이동 · prefs 저장 (0.3.10).
97은 문장/그림 더블탭으로 전체 화면 · 다시 더블탭 원복 (0.3.11).
98은 분할 바 드래그 · 기본 자석 · 끝 텐션 스냅 (0.3.12).
99는 모바일 번역 설정 옵트인 · ingest/open `?translate=` (0.3.13).
100은 읽기 프레임 헤더 탭 토글 · 분할 시 양쪽 동기 (0.3.14).
101은 보관 목록 길게 눌러 드래그 순서 변경 (0.3.15).
102는 보관 휴지통 삭제 · GCS·노트·쉐도잉 기록 정리 (0.3.16).
103은 모바일 TTS 목소리·랜덤 난이도 · 읽기·연습 공유 (0.3.17).
104는 설정 초대 코드 칸을 승인·관리자에게 숨김 · Deny 재입력 (0.3.18).
105는 업로드 실패 알림 · 인제스트 폴링 20분 (0.3.19).
106은 품질 단계 Gemini 타임아웃 · GCS +1% 진행률 반영 (0.3.20).
107은 Cloud Run 인스턴스 간 ingest job lease·재시작 (0.3.21).
108은 보관 cache 없이「완료」금지 · 실패 시 blob 유지 (0.3.22).
109는 보관함 인제스트 에러 닫기 · terminal 시 초안 정리 (0.3.23).
110은 ingest checkpoint 봉투 · TTL/버전 폐기 (0.3.24).
111은 ingest `want_chunks` NameError 복구 · open JSON 실패 (0.3.25).
112는 ingest checkpoint payload를 소비해 mid-stage skip (0.3.26).
113은 shadowing chunk build 시간 예산·이어하기로 HTTP 504 회피 (0.3.27).
114는 보관 열기 시 빈 세션 거절 · 로컬 빈 session이면 GCS 재pull (0.3.28).
115는 읽기 AnimatedContainer clipBehavior+decoration 없음 crash → ClipRect (0.3.29).
116는 그림 핀치가 부모 스와이프 드래그에 안 지게 제스처 분리 (0.3.30).
117는 그림 넘기기를 한 손가락 제스처만 허용 (핀치→1× 오인 스와이프 금지) (0.3.31).
118는 그림 핀치 스케일을 증폭해 같은 손가락 이동이 확실히 체감되게 (0.3.32).
119는 shadowing chunks/build raw 500 차단 · pending 이어받기 · 빈 성공 배너 금지 (0.3.33).
120은 쉐도잉 「다시」(말하기만) · 「다시 듣기」(내 녹음) · 횟수 제한 없음 (0.3.34).
121은 보관 열기 시 소유자 GCS를 항상 pull · 실패 시 로컬 폴백 금지 (0.3.35).
122는 보관 목록 드래그 시 Material 흰 섬광 제거 · proxyDecorator (0.3.36).
123은 진행 복원 문장+그림 정밀 · 이상값 fail-closed · 앱 prefs (0.3.37).
124는 빠진 그림 정직한 빈 슬롯 · 앱 Fig.N 점프 칩 (0.3.38).
125 — 캡션 우선 그림 추출 (0.3.39).
126–129 — soft caption · Elsevier join · column clip · lazy figure open (→0.3.45).
130 — 클라우드 오류 로그 · 관리자 배지 · hang/repeat 탐지 (0.3.47).
131 — 캡션 전문 표시 · server normalize ceiling (0.3.47).
135–137 — cover · strip adjacent · caption lumps (→0.3.55).
138 — 로컬 서버 흔적 제거 · Live+폰만 (0.3.56).
139 — Fig. 점프 칩 정식화 · 앱+웹 문장 아래 (0.3.57).
142 — 키보드 문장 노트 제거 · 녹음 연습 유지 (0.3.58).
143 — 스와이프 방향 관례 정정 · 왼쪽=다음 (0.3.59).
144 — 보관 TTL 90일 · ⚠️ 경고 · +90일 연장 · lazy purge (0.3.60).
145 — 보관 재분석 앱 UI · translate 설정 연동 (0.3.61).
146 — 보관 연장 +90일 (0.3.62 · design/144 tweak).
146a — 앱 계정 연결/해제 · Settings (0.3.63).
146c — 카카오 OAuth scheme hyphen fix (0.3.64).
146b — 계정 창고 병합 (후보 · 미구현).
140 — Flutter MVP 백로그 쪼개기 · next=141 노트 (docs).
141 — 모바일 문장 노트 설계 잠금 (구현 전).
160 — 보관 메타 줄 · Title Page 네비 · 연습 GCS/auto-off · 설정 3스위치 · 북마크 배지 (0.3.94).
161 — 설정 APK 다운로드 행 · 북마크 문구 (→0.3.95).
162 — 연습 카메라 미러 · 보관 만료 날짜 · 설정 TTS 여백 (0.3.96).
163 — Figure layout edit v2 · page_preview · commit (0.3.99).
164 — Fig-ref 패널 폴백 (0.3.99).
167 — debone 품질 가드 · chunk split fallback · warnings·ingest_quality 영속 · Body 진단 (→0.3.100).
166 — 모바일 주석 MVP · annotations/sync · 문장 long-press · 4색 하이라이트 (→0.3.100, 167 이후 reanchor).
168 — ingest·open·figures **과잉 계측** · phase machine · T1–T10 불변식 · silent catch 제거 · sweeper (→0.3.112, **버그 수정 전 필수**). 체크리스트: [168-audit-checklist.md](168-audit-checklist.md).
169 — **Agent Evidence Bus** 전역 증거 수집 · 오류 개선 전용 · 관리자/사용자 UI 없음 · `asr/evidence/` + `pull_evidence.py` (168/130과 분리). 체크리스트: [169-audit-checklist.md](169-audit-checklist.md).
172 — access/status 타임아웃 시 sticky unlock · 승인대기 튕김 방지 (0.3.147).
