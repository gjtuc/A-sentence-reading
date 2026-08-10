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


## User-facing copy (0.2.82)

Settings invite help is **minimal**: do not expose server generation, example codes, or Allow/paid-API wording to end users. Ops docs above keep format examples for admins.


## Admin emails ops (0.2.82)

### Settings auth→access reload (0.2.82)

Flutter Settings must re-fetch `/api/access/status` when `AuthController` becomes logged in.
`initState` alone races session restore and left `is_admin` chrome hidden even when `ASR_ADMIN_EMAILS` matched.



- Set GitHub secret / Cloud Run env `ASR_ADMIN_EMAILS` (comma list). **Do not commit real addresses.**
- `scripts/deploy_cloud_run.sh` has **no hardcoded default** — empty list ⇒ nobody is admin (mint/decide fail-closed).
- Deploy logs print `configured_count` only, not addresses.
- Flutter Settings mint UI appears only when `/api/access/status` returns `is_admin: true` (session email ∈ list).

## Version

Web **0.2.98** · `access_gate` / `mobile_access_gate` · `access_gate_gcs` · `mobile_invite_copy_minimal` · `mobile_admin_emails_configured` · `mobile_shell_nav` · pubspec `0.2.98+1`

GCS durability for invites/events/redeem: [69-access-gate-gcs.md](69-access-gate-gcs.md).


## Hardening (0.2.82)

| Control | Default | Env |
|---------|---------|-----|
| Invite TTL | 48h | `ASR_INVITE_TTL_HOURS` (`0` = no expiry) |
| Redeem rate limit | 10 / 900s per uid | `ASR_INVITE_REDEEM_MAX` · `ASR_INVITE_REDEEM_WINDOW_SEC` |

- Expired open codes → status `expired` · API `409 code_expired`
- Excess redeem attempts → `429 rate_limited` (empty code does not count)
- Mint response includes `expires_at` / `ttl_seconds`
- Live Enable / IPS → Trading Gate only (ASR out)


## Admin UI gate (0.2.82)

- `/api/access/status` includes `is_admin` (from `ASR_ADMIN_EMAILS`)
- Flutter Settings shows mint/pending/Allow **only** when `is_admin: true`
- Non-admin still gets server `403 admin_required` on mint/decide (defense in depth)
- Live Enable / IPS: Trading Gate (ASR out) — unchanged this chip


## Invite redeem E2E (0.2.86)

Device path (two identities — do not paste OTP/emails in chat/PR):

1. Admin mints OTP once
2. Second account redeems → `pending` (paid blocked)
3. Admin Allow
4. Invitee taps **새로고침** → `allowed` · paid OK

### Session isolation (0.2.86)

Settings clears `_minted` / invite field / access lists on logout so the next account cannot see the previous OTP or typed code (fail-closed for account switch on one device).

Live Enable / IPS: Trading Gate only (ASR out) — unchanged this chip.

### Allow during refresh (0.2.86)

Settings uses `_mutating` for Allow/Deny so a concurrent **새로고침** (`_loading`) cannot swallow the admin tap (invitee would otherwise stay `pending`).

