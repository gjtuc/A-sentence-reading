# 158 — Ingest idle timeout + 「이어서 분석하기」

**Version:** 0.3.87 (+ 0.3.138 auto-resume / 60s poll HTTP)  
**Scope:** mobile ingest poll + library resume UX (no server change).

---

## 0.3.138 — poll HTTP 60s + stage-scoped auto resume

| Rule | Behavior |
|------|----------|
| Poll/chunk create GET timeout | **60s** (was 30s) — fewer false `TimeoutException` |
| Same stage timeout ×1–3 | Auto 「이어서 분석하기」 |
| Same stage ×4+ | Stop auto; user taps button |
| New stage | Counter resets |

Files: `ingest_auto_resume.dart`, `library_controller.dart`, `client.dart` (`pollIngestJob` GET).

---

## ⚠️ APK 설치 대기 (사용자 확인 필수)

**0.3.87 APK는 아직 폰에 설치되지 않았습니다.**

다음 채팅에서 무엇을 하든 **먼저** SM-G986N에 0.3.87 APK를 설치해야 이 기능이 동작합니다.

```bash
# 빌드 후 (에이전트 또는 로컬)
MSYS2_ARG_CONV_EXCL='*' "/c/Users/user/Downloads/scrcpy-win64-v3.3.1/adb.exe" install -r mobile/build/app/outputs/flutter-apk/app-release.apk
```

Cloud Run 0.3.87 배포만으로는 모바일 UX가 바뀌지 않습니다.

---

## Problem

- `pollIngestJob` had a fixed **20-minute wall-clock** timeout → long jobs looked “stuck” even when the server was still working.
- On 504 / hang, users had no visible **resume** affordance despite `UploadDraft` + `resumePendingIfAny()` existing.

## Solution

### 1. Idle + max poll timeout (`client.dart`)

| Parameter | Default | Behavior |
|-----------|---------|----------|
| `idleTimeout` | 5 min | Resets when `percent` or `message` changes |
| `maxDuration` | 2 h | Absolute safety cap |

504 messages:

- Idle: `분석 진행이 멈춘 것 같습니다. 아래 「이어서 분석하기」를 눌러 주세요.`
- Max: `전체 처리 시간이 너무 깁니다. 잠시 후 「이어서 분석하기」를 눌러 주세요.`

### 2. Resume offer (`library_controller.dart`)

- `resumeOfferVisible` when a resumable draft exists (`job_id` + `phase: processing`) and not actively uploading/reanalyzing.
- `resumeAnalysis()` → `resumePendingIfAny()`
- `discardResumeDraft()` clears draft + hides offer.
- 504 / ingest hang keeps draft; 422/404/409 still clear.

### 3. Library UI (`library_screen.dart`)

- **이어서 분석하기** `FilledButton` when `resumeOfferVisible`.
- **초안 삭제** `TextButton`.
- **지금 이어가기** when `uploadStalled` (45s no progress).

## Invariants

- Existing auto-resume on app open (`_loadAndResume`) unchanged.
- Stall (45s) ≠ failure; hang watchdog (3 min) ≠ idle timeout (5 min no server change).

## Implementation

| Piece | Path |
|-------|------|
| Poll idle/max | `mobile/lib/api/client.dart` → `pollIngestJob` |
| Resume state | `mobile/lib/state/library_controller.dart` |
| Buttons | `mobile/lib/screens/library_screen.dart` |
| Tests | `mobile/test/ingest_client_test.dart` |
