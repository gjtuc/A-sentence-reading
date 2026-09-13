# 262 — Documents/문장읽기 external mirror

Version: **0.3.260** · Status: **locked** (design only — impl phased 264+)  
Amends [185](185-local-paper-sot.md) · [186](186-device-transfer-pack.md) · [187](187-local-user-artifacts.md)

## Intent

Survive **uninstall / clear data** on the same device via public
`Documents/문장읽기/{uid}/…` (not app-private “Documents”).

## Locked product (from Q&A)

| Rule | Detail |
|------|--------|
| Scope | Almost everything; **shadowing chunks YES**, **voice recordings NO** |
| Path | Fixed `Documents/문장읽기/{uid}/…` — **no SAF pick** |
| Storage API | **MES** + Kotlin MethodChannel (sideload); not MediaStore primary; not import MES (226/242 carve-out) |
| SoT | In-app primary; external fills **only when empty** |
| Restore | Login + empty in-app → **auto**, no confirm |
| Cursor flush | On return to library tab |
| Fail | Visible banner; never fake success |
| 185 wipe | **Keep** cloud papers wipe |
| 186 | Settings **manual** upload only |

## Fail-closed (summary)

No session token / voice / SAF grants / soft-delete prefs in mirror. Wrong uid
refuse. Hard delete syncs external. Kill: `ASR`-style client flag later.

## Impl phases (not this ship)

264 MES channel · 265 paper write · 266 empty-gate restore · 267 chunks/cursor.

## Version

**0.3.260** (design lock) · code starts **0.3.264+**
