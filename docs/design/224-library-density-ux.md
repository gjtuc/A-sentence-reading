# 224 — Library density UX (nav merge · soft-delete · TTS simplify)

Version: **0.3.223** · Status: **locked**  
Depends: [68](68-mobile-shell-nav.md) · [102](102-library-delete.md) · [177](177-delete-honesty.md) · [101](101-library-reorder.md) · [64](64-mobile-tts.md) · [212](212-tts-skill-tier.md)

## Locked MVP (this ship)

| Include | Exclude (later chips) |
|---------|------------------------|
| TTS UI: **사용자 선택** (`fixed`) / **랜덤** (`random_auto`) only | Drop legacy rate-band constants from runtime maps |
| Settings gear on library chrome; **no Settings bottom tab** | AccessWaiting gear |
| Single flow: library ↔ reader (Offstage keep-alive); **no 읽기 tab** | Nested reader Navigator rewrite |
| System back: nested routes → reader→library → exit edit → app | Magnetic trash snap |
| Long-press → edit mode; trash **only in edit**; multi soft-hide | Multi-item block reorder |
| Soft-hide + wall-clock `purge_at` (+60s) + SnackBar undo | Server tombstone; kill-resume undo UI |
| design/177 honesty on **hard** DELETE only | Soft-hide HTTP |

## INVARIANT

- Soft-hide SoT = uid-scoped prefs `asr.lib_soft_del.v1.u.$safeUid`
- Merge/refresh/handoff **must** filter `hiddenIds` or rows resurrect
- Hard purge = existing `deletePapers` (HTTP ok → drop row / disk)
- TTS: **migrate before normalize**; UI set = `{fixed, random_auto}`
- Labels: fixed→「사용자 선택」, auto→「랜덤」
- Reader surface keeps widget alive (P1 Offstage + TickerMode)

## Flows

1. 보관 → 톱니 → Settings push → back → 보관  
2. 보관 → open → 읽기 surface → system back → 보관 (session kept)  
3. long-press row → edit + checkbox; trash → soft-hide → SnackBar 실행 취소 (≤60s)  
4. App start / resume → purge due (`purge_at <= now`) via DELETE  
5. Legacy TTS mode prefs → `random_auto` + skill tier

## Evidence

- `nav_surface` `{surface: library|reader}`
- `nav_settings_open`
- `paper_soft_hide` `{n, purge_at_ms}`
- `paper_soft_undo` `{n}`
- Existing `paper_delete_*` on hard purge only

## Non-goals

- Magnetic trash / multi-drag reorder  
- Upload cancel banner on reader (follow-up)  
- Bundle with AccessWaiting / evidence floor / ingest

## Version

**0.3.223**
