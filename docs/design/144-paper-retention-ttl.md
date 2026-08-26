# 144 — Paper retention TTL (90d · warn · extend · purge)

Modules: `paper_retention.py` · `paper_cache.py` · `papers_gcs.py` · `/api/cache/papers*` · `library_screen.dart`  
받침: [18](18-paper-library.md) · [102](102-library-delete.md)

## 무엇인가

논문 보관 **번들**(session·figures·source·노트·쉐도잉·voice)에 **만료 시각**을 둔다.  
기본 **90일** 후 삭제 · 만료 **30일 전** ⚠️ · **+14일** 연장(30일 이내만) · 읽는 중 만료 **+3일** grace.

| 포함 | 미포함 |
|------|--------|
| index `expires_at` · list `retention` · extend API · lazy purge | 웹 보관 UI (145 후보) |
| 앱 보관 ⚠️ + 연장 | Cloud Scheduler 배치 (147) |
| 재분석 성공 → 90일 리셋 | TTS orphan GC |
| kill `ASR_PAPER_RETENTION=0` | Live Enable / IPS |

## Product (locked)

1. **기본:** `expires_at = created/saved + 90일` (읽기만으로는 안 늘림)  
2. **경고:** `days_until_expiry <= 30` → 보관 행 ⚠️  
3. **연장:** 30일 이내 +14일 (반복 가능) · `POST …/extend-retention`  
4. **재분석** ingest 저장 성공 → **90일 리셋**  
5. **기존 보관분** `expires_at` 없음 → **최초 조회 시 now+90** (배포일 기준 공평 시작)  
6. **읽는 중 만료:** open 또는 cursor 중 `now >= expires_at` → **+3일** (같은 `expires_at`에 grace 1회)  
7. **만료 후** grace도 지나면 purge (`delete_cached_paper` · design/102)

## Kill / rollback

- `ASR_PAPER_RETENTION=0` → TTL off (no purge · no warn fields)  
- Revert PR

## Version

**0.3.60**

## Live Enable / IPS

이번 칩에서 불필요함.

## Device / E2E pin

- Live `/api/status`: `version=0.3.61` · `paper_retention=true` · days 90/30/14/3 (E2E closure re-check 2026-08-26)
- pytest `tests/test_paper_retention.py` — 7 passed (extend API mocked · kill switch · mobile wiring)
- Phone SM-G986N: APK `0.3.61` · 보관 탭 로드 OK
- **⚠️/연장 UI: 해당 없음 (이번 E2E)** — 신규 ingest 직후 `days_until_expiry` ≫ 30 → ⚠️ 버튼 0건 (`content-desc="보관 기한 임박"` 미표시). warn/extend sheet는 만료 30일 이내 데이터로 별도 칩(147 spillover)에서 재확인.
- **재분석 → TTL 리셋:** 145 E2E closure와 동일 세션에서 재분석 snackbar 성공(간접 확인; expires_at 필드는 UI 미노출)
- Kill: `ASR_PAPER_RETENTION=0` · revert PR

Do not paste emails, cookies, tokens, or secrets into chat/PR.
