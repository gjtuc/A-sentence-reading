# 33 — Android Flutter 앱 (문장 읽기)

모듈 (예정): `mobile/` (Flutter) · 기존 Cloud Run API (`src/sentence_reading/`)

## 무엇을

PC **웹**은 유지하고, 휴대폰용 **네이티브 앱**을 새로 둔다.

| 항목 | 결정 |
|------|------|
| 표시 이름 | **문장 읽기** |
| 플랫폼 | **Android만** (iOS 없음 · 이번 범위) |
| 스택 | **Flutter** (단일 메인 스택 · Kotlin 병행 앱 없음) |
| 백엔드 | **기존 Cloud Run API** (Gemini·GCS·TTS는 서버) |
| 배포 | 당분간 **APK 사이드로드** (Play Console 아직 없음) |
| 긴급도 | 급하지 않음 — 설계 → MVP 스캐폴드 → 실기 확인 |

## 제품 역할 분담

| | PC 웹 | 모바일 앱 |
|--|-------|-----------|
| 주 용도 | 기관망에서 PDF **ingest·다듬기** | 보관된 논문 **읽기** |
| 홈 | 업로드·보관 병행 | **최근/보관 목록 우선** |
| 업로드 | 1급 | 있음 · **2급** (메뉴/보조) |
| 인증 | Google · 카카오 · 이메일 | **동일 전부** |
| 테마 | (웹 기존) | **시스템 / 라이트 / 다크** 선택 |

불변조건(문장↔그림 독립, 한 문장만, AI 채점 없음)은 [PRODUCT.md](../PRODUCT.md)와 동일.

## 비목표 (MVP)

- Play Store / Play Console 등록
- iOS · 태블릿 전용 레이아웃
- 앱 안에 Gemini·GCS 키 넣기 (**금지** — 서버만)
- Flutter + 별도 Kotlin 앱을 둘 다 메인으로 유지
- 음절·품사 색 (웹과 동일 · 하지 않음)
- 앱 아이콘 정교화 (나중에)

## MVP 범위 (“먼저 최소”)

1. **로그인** — Google · 카카오 · 이메일 (쿠키/세션을 Flutter HTTP 클라이언트가 유지)
2. **보관 목록** — `GET /api/cache/papers` → 항목 탭 → open
3. **읽기** — 한 문장 · 그림 패널 · ←/→ 문장 · 그림 독립 이동
4. **TTS** — `POST /api/tts` (서버 합성 · 앱은 재생·배속 UI만)

후속(설계만, MVP 밖): 노트·리비전·계정 연결 UI·재분석·Fig 점프 칩·복합 그림 세부·사용량.

## API 재사용

베이스 URL (운영):

`https://asr-sentence-reading-984608876300.asia-northeast3.run.app`

앱은 **새 백엔드 없이** 기존 계약을 쓴다 ([04](04-api-contract.md) · [18](18-paper-library.md) · [15](15-tts-and-gestures.md) · [23](23-multi-auth-link.md)).

| MVP에서 쓰는 것 | 용도 |
|-----------------|------|
| `GET /api/status` | 헬스 · 버전 배지 |
| `/api/auth/*` | Google · 카카오 · 이메일 |
| `GET /api/cache/papers` · `…/open` | 보관 → 세션 |
| `GET /api/session/{id}` · cursor PATCH | 문장/그림 커서 |
| `/media/…` | 그림 PNG |
| `POST /api/tts` · voices | 재생 |

`POST /api/ingest` 는 업로드 화면에서만 (2급).

### 인증 주의 (모바일)

- 웹은 브라우저 쿠키. Flutter는 `CookieJar` / `dio` 등으로 **Set-Cookie 유지**.
- 카카오: Redirect URI에 **커스텀 스킴 또는 App Link** 추가 필요 (콘솔에 등록).  
  예: `com.gjtuc.sentence_reading://oauth/kakao` (최종 스킴은 구현 시 확정).
- Google: GIS 웹 플로우 대신 **Android OAuth 클라이언트** + 서버 `POST /api/auth/google` 토큰 교환(기존 계약에 맞춤). 서버 계약이 웹 id_token만이면 **동일 엔드포인트**로 id_token 전달.
- 이메일: 기존 register/login JSON 그대로.

## 화면 (MVP)

```
[로그인] ──► [보관 홈] ──► [읽기]
                │              ├ 문장 패널 (1문장)
                │              ├ 그림 패널
                └ [업로드]     └ TTS / 테마 / 로그아웃
```

1. **로그인** — 세 수단 스택 · 실패 메시지 [08](08-errors.md) 톤
2. **보관 홈** — 최근/목록 · 빈 상태 안내 · (보조) 파일 선택 업로드
3. **읽기** — 세로 우선: 위 문장 · 아래 그림(또는 스플리터) · 제스처/버튼으로 문장·그림 독립 이동
4. **설정** — 테마(system/light/dark) · TTS 모드/보이스(웹 `asr.tts.v2` 개념을 SharedPreferences로)

## 패키지·프로젝트 레이아웃

| | |
|--|--|
| applicationId | `com.gjtuc.sentence_reading` (영문 · 잠정) |
| 레포 위치 | `mobile/` (monorepo 루트 하위 · 웹 `src/`와 분리) |
| 최소 SDK | Android 8+ (API 26) 권장 · 구현 시 확정 |

웹 CD([32](32-github-cd.md))와 **별 트랙**: MVP는 로컬 `flutter build apk`.  
앱 스토어/CI APK는 이후 문서에서.

## 테마

- 기본: **시스템**
- 사용자 선택: light / dark / system → `SharedPreferences`
- Immersive Reader식 문장 타이포는 [07](07-typography-tokens.md) 수치를 Flutter Theme로 이식 (완전 동일 픽셀 불필요 · “한눈에 한 문장” 감각 유지)

## 합격 기준 (설계 → 구현 시)

- [x] `mobile/` 스캐폴드 · status 클라이언트 · 화면 자리 (0.2.55 · [47](47-flutter-scaffold.md))
- [x] `android/` 플랫폼 · applicationId · 라벨 「문장 읽기」 (0.2.56 · [48](48-flutter-android-platform.md))
- [x] 이메일 로그인·세션 쿠키 (0.2.82 · [61](61-mobile-email-auth.md)) — 수단 1/3
- [x] Google·카카오 앱 로그인 배선 (0.2.82 · [65](65-mobile-oauth.md)) — 수단 3/3
- [x] 액세스 게이트 OTP·Allow/Deny (0.2.82 · [67](67-access-gate.md))
- [ ] APK를 실기에 설치해 Cloud Run에 로그인 확인 — Android SDK 있는 환경
- [x] 보관 목록에서 논문 열고 문장·그림 독립 이동 (0.2.70–0.2.71 · [62](62-mobile-library.md)·[63](63-mobile-reader.md))
- [x] 현재 문장 TTS 재생 (0.2.82 · [64](64-mobile-tts.md))
- [x] 테마 3종 전환 유지(재실행 후) (0.2.82 · [66](66-mobile-theme.md))
- [x] 앱 소스에 Gemini/GCS secret **없음** (계약 테스트)

## 구현 순서

1. ~~`mobile/` 스캐폴드 · 표시명 「문장 읽기」 · `/api/status`~~ (**0.2.55**)
2. ~~`flutter create` → `android/` · applicationId~~ (**0.2.56**)
3. ~~이메일·보관·읽기·TTS·Google/카카오~~ (0.2.69–0.2.82)
4. ~~테마 3종~~ (0.2.82) · release APK · 실기 사이드로드 (Android SDK)

## Live Enable / IPS

**Stock Trading Gate 전용.** 이 레포·Flutter 앱에 구현하지 않는다 ([47](47-flutter-scaffold.md) · [48](48-flutter-android-platform.md)).

## 버전

웹 **0.2.82** · `access_gate` · pubspec `0.2.82+1`

## Access gate pin (0.2.83)

Invite redeem E2E + Settings logout clears minted OTP (see [67](67-access-gate.md)).

## Shell nav pin (0.2.86)

Auth gate + tabs 보관/읽기/설정 · account/server under Settings (see [68](68-mobile-shell-nav.md)).

## Sideload APK pin (0.2.86)

Samsung device `versionName` matches pubspec / live API **0.2.86** after `flutter build apk` + `adb install -r` (see [48](48-flutter-android-platform.md) Device E2E). Prior gap: phone stayed on 0.2.84 while Cloud Run was already 0.2.86.

## Mobile upload pin (0.2.98)

Single PDF from 보관 → Cloud Run ingest → user GCS (see [70](70-mobile-upload.md)).

