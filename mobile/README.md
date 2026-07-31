# 문장 읽기 — Android Flutter

Application id: `com.gjtuc.sentence_reading`

Design: [33](../docs/design/33-mobile-flutter.md) · [61](../docs/design/61-mobile-email-auth.md)–[67](../docs/design/67-access-gate.md).

## Status (0.2.78)

- Scaffold baseline **0.2.56**
- Login · library · reader · TTS · theme
- **Access gate**: OTP invite (48h TTL · redeem rate limit) (`XXXX-XXXX`) + admin Allow/Deny before paid APIs
- Live Enable / IPS: Trading Gate (ASR out)

## Access codes

Admin Settings → mint → copy `TqG3-V12T`-style code (shown once).  
User Settings → paste code → pending → admin Allow.

## Out of scope

- Live Enable / IPS
- Secrets in the APK
- BYOK (follow-up)
