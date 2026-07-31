# 67 — Access gate (OTP invite + admin allow/deny)

Modules: `llm/access_gate.py` · `/api/access/*` · Flutter settings  
See: [33-mobile-flutter.md](33-mobile-flutter.md) · [23-multi-auth-link.md](23-multi-auth-link.md) · [27](27-usage-meter.md)

## What

Cost protection for Cloud Run / Gemini / TTS / GCS:

1. Admin mints a **random OTP-style code** `XXXX-XXXX` (e.g. `TqG3-V12T`) — not chosen by humans
2. User logs in → enters code → status **pending**
3. Admin **Allow** / **Deny**
4. Only `allowed` (or admin / gate-off) may call paid APIs
5. Failed/pending attempts append admin notifications

| In | Out (follow-up) |
|----|-----------------|
| Single-use hashed invites | BYOK (own API keys) |
| Admin mint / pending / decide | Email push alerts |
| Paid API 403 `access_denied` | Live Enable / IPS |

## Code format

- Alphabet without ambiguous `0 O 1 I L`
- Display `ABCD-EFGH`; input may omit dash/spaces
- Server stores **SHA-256 only**; plaintext shown **once** at mint

## Env

| var | meaning |
|-----|---------|
| `ASR_ACCESS_GATE` | `0` off · `1` on · unset → **on** |
| `ASR_ADMIN_EMAILS` | comma list — mint/decide/notifications |

## API

| | |
|--|--|
| `GET /api/access/status` | gate + user status |
| `POST /api/access/invite` | `{ code }` → pending |
| `POST /api/access/admin/mint` | → `{ code }` once |
| `GET /api/access/admin/pending` | queue |
| `GET /api/access/admin/notifications` | events |
| `POST /api/access/admin/decide` | `{ uid, decision: allow\|deny }` |

## Non-goals

- Half-key embedded in APK (extractable)
- Live Enable / IPS (Trading Gate)

## Version

Web **0.2.79** · `access_gate` / `mobile_access_gate` · pubspec `0.2.79+1`


## Hardening (0.2.79)

| Control | Default | Env |
|---------|---------|-----|
| Invite TTL | 48h | `ASR_INVITE_TTL_HOURS` (`0` = no expiry) |
| Redeem rate limit | 10 / 900s per uid | `ASR_INVITE_REDEEM_MAX` · `ASR_INVITE_REDEEM_WINDOW_SEC` |

- Expired open codes → status `expired` · API `409 code_expired`
- Excess redeem attempts → `429 rate_limited` (empty code does not count)
- Mint response includes `expires_at` / `ttl_seconds`
- Live Enable / IPS → Trading Gate only (ASR out)


## Admin UI gate (0.2.79)

- `/api/access/status` includes `is_admin` (from `ASR_ADMIN_EMAILS`)
- Flutter Settings shows mint/pending/Allow **only** when `is_admin: true`
- Non-admin still gets server `403 admin_required` on mint/decide (defense in depth)
- Live Enable / IPS: Trading Gate (ASR out) — unchanged this chip
