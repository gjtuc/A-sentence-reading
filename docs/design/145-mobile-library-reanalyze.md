# 145 — Mobile library reanalyze (design/20 parity)

Modules: `mobile/lib/screens/library_screen.dart` · `library_controller.dart` · `client.dart` · `POST …/reanalyze`  
받침: [20](20-source-backup.md) · [140](140-mobile-mvp-backlog-split.md) · [99](99-mobile-translate-opt-in.md)

## 무엇인가

보관 목록에서 **원본 백업이 있는 논문**을 앱에서 「재분석」 — 웹 `app.js` 와 동일 API · job 폴링.

| 포함 | 미포함 |
|------|--------|
| `has_source` 행 · 재분석 버튼 · 진행률 · fail-closed | 확인 팝업 (바로 시작) |
| `translate=0|1` query (설정 탭 번역 토글) | ingest cancel during reanalyze |
| 서버 job `want_translate` from query | 웹 UI 변경 · APK self-update |
| pytest wiring + phone E2E (은규 PDF) | Live Enable / IPS |

## Product (locked)

1. **표시:** `has_source == true` → 보관 행 「재분석」(웹과 동일; stale 여부 무관)  
2. **동작:** 탭 즉시 `POST /api/cache/papers/{id}/reanalyze?translate=0|1` → `/api/ingest/jobs/{id}` 폴링  
3. **번역:** 설정 탭 「번역 사용」 ON → `translate=1`, OFF → `translate=0` (design/99)  
4. **동시성:** 업로드·열기·삭제·재분석 중 다른 재분석/업로드 금지  
5. **완료:** 목록 refresh · 실패 시 snackbar/배너 (성공한 척 금지)  
6. **cache_id:** 서버 `skip_cache` + `content_hash` 기존 id 유지 (design/20)

## Kill / rollback

- Revert PR · 앱 버튼 제거 (API unchanged)

## Version

**0.3.61**

## Live Enable / IPS

이번 칩에서 불필요함.

## Device / E2E pin

- Live `/api/status`: `version=0.3.61` (post-CD 2026-08-26)
- pytest `tests/test_mobile_library_reanalyze.py` + full suite 683 passed
- Phone SM-G986N: APK `0.3.61` sideload · library tab OK · `asr_e2e145.pdf` pushed to `/sdcard/Download/`
- **재분석 탭→완료 snackbar: 미실시** — 보관 0건; file picker 후 Android 「연결 프로그램」에서 앱 복귀 실패 (upload 미완료). PC `PC\차헌의 S20+\SD 카드\은규 논문` 경로 이 PC에서 미발견.
- Kill: revert PR

Do not paste emails, cookies, tokens, or secrets into chat/PR.
