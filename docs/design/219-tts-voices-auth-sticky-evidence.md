# 219 — TTS voices auth sticky evidence

**Parent:** [169](169-agent-evidence-bus.md) · [15](15-tts-and-gestures.md) · [83](83-login-required-gate.md)  
**Version:** 0.3.219+  
**UI:** 읽기 탭 `tts.error` (스피커 아래) — 제품 UI 없음

---

## Problem (evidence gap)

Live red line `AsrApiException(로그인 후 이용해 주세요., status=401)` under sentence chrome was **inferred** as:

1. `GET /api/tts/voices` + login gate (design/83)
2. `TtsController.ensureVoicesLoaded` → `error = e.toString()` (sticky)
3. Login later does not re-fetch voices → sticky UI while settings shows logged-in

**Missing at incident time:** device log of the failing route, `has_token`, bootstrap vs post-login phase, server-side deny breadcrumb for `/api/tts/voices`, and proof that sticky survived auth.

## Locked sensors (overkill OK)

| Kind | Source | When |
|------|--------|------|
| `tts_voices_call_start` | mobile | every `ensureVoicesLoaded` attempt |
| `tts_voices_call_done` | mobile | success/fail; `http_status`, `has_token`, `stage` |
| `tts_auth_sticky` | mobile | auth error string still in `tts.error` while logged in; also pre-retry |
| `login_gate_deny` | server middleware | anonymous 401 on `/api/tts*` (always) |
| `client_api_fail` | mobile | existing; `POST /api/tts` 401 now breadcrumbed too |

### `details` (snake-safe only)

- `has_token` int 0/1  
- `voice_n` int  
- `stage` via event `stage`: `bootstrap` \| `login_retry` \| `manual_reload` \| `force`  
- `sticky` int 0/1 on done when error kept for UI  
- `code`: `auth_required` \| `ok` \| `other`

## Product fix (same ship)

On auth bind (`_syncPrefsFromAuth` logged-in path): `ensureVoicesLoaded(force: true, stage: login_retry)` so sticky 401 clears after login.

## Agent pull

```bash
python scripts/pull_evidence.py --since 2h --kind tts_voices_call_start,tts_voices_call_done,tts_auth_sticky,login_gate_deny,client_api_fail
```

Join: same `trace_id` / time window — `login_gate_deny` route=`/api/tts/voices` then mobile `tts_voices_call_done` `http_status=401` `has_token=0|1`.

## Non-goals

- Making `/api/tts/voices` public (catalog stays behind login)
- Sentence text in evidence
- Shrinking evidence floor
