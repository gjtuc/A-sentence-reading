# 181 — Figure PNG self-contained + hydrate honesty

**Parent:** [180](180-figure-hydrate-reliability.md) · [129](129-lazy-figure-open.md) · [121](121-gcs-open-fail-closed.md)  
**Status:** DESIGN FROZEN → ship **0.3.164**  
**Trigger:** 2026-09-07 live 0.3.163 hydrate `d3b349a35000`: 12/14 ok; **fail index 2** (`timeout` 120s), **fail index 13** (`missing` + server `session_meta_missing`). User sticky `TimeoutException after 0:02:00` during concurrent reader open.

---

## 0. Success definition (user-visible)

| Pass | Fail |
|------|------|
| Library row has **no** `그림 N장 받지 못함` after hydrate | Any `figure_hydrate_partial` with `failed > 0` when GCS has the PNG |
| Sticky library banner is **not** raw `TimeoutException...` from hydrate/open races | English TimeoutException sticky |
| Evidence: `figure_hydrate_done` with `filled == total` on retest paper | Claiming “180 works” while 2 figures missing |

180 remains locked (per_png · single figure net gate · miss retry · add-only floor).  
181 **adds** self-contained PNG + honesty; does not undo 180.

---

## 1. Locked judgments

| # | Judgment |
|---|----------|
| J1 | PNG GET is **self-contained**: if local `session.json` is missing **or** GCS papers are ready, ensure session via the same fail-closed path as open (`refresh_paper_for_open` / `download_paper_cache(..., include_figures=False)`). **Never** serve another user’s leftover when GCS pull fails. |
| J2 | Process-local **session ensure TTL ≤ 60s** per `cache_id` so 14 sequential PNGs do not re-download session every time on the same instance. |
| J3 | PNG bytes are **`path.read_bytes()`** — no data-URL encode/decode round-trip on the PNG GET path. |
| J4 | Server `figure_png_done` includes `session_ensured`, `pull_ms`, `read_ms`, and honest `outcome`/`reason`. |
| J5 | Client `figure_png_done`: `TimeoutException` → `outcome=timeout`; other network errors → `outcome=network`; 404 carries server `reason`. |
| J6 | Hydrate **must not** assign `LibraryController.error` from PNG failures. Reader `open` TimeoutException uses a **Korean** sticky message (not `e.toString()`). |
| J7 | While hydrate is active for `cache_id`, reader `open` of that id **reuses** `_hydrateSessions[cacheId]` when valid (avoids open∩PNG LTE contention). |
| J8 | Miss retry **skips** non-retriable reasons: `figure_id_not_in_meta`, `bad_figure_id`, `bad_cache_id`, `bad_file_rel`, `path_escape`. |
| J9 | PNG client timeout **180s** (was 120). Still one-in-flight gate (180 J1). Not a substitute for J1–J3. |
| J10 | During `_hydrateActive.isNotEmpty`, `_wantTranslate` **must not** call `fetchAuthStatus` (use Settings callback / prefs only) to reduce auth timeouts under PNG load. |
| J11 | Add-only evidence floor. Ship **0.3.164**. |

---

## 2. Server

### 2.1 `figure_png_lookup` (new) / `figure_png_bytes_with_reason`

```
validate ids
ensure_session_for_png(cid):  # J1+J2
  if gcs ready:
    if no local meta OR ttl expired:
      refresh_paper_for_open(cid)  # figures=False
      if gcs_pull_failed → (None, gcs_pull_failed)  # no leftover
  else:
    if no local meta → session_meta_missing
resolve fid → rel (existing security)
ensure_figure_local_with_reason
read_bytes → raw
```

### 2.2 API `cache_figure_png`

Emit denser `figure_png_done` details; 404 JSON keeps `reason`.

---

## 3. Mobile

- `fetchFigurePng`: 180s timeout; parse 404 `reason`; honest outcomes; optional `reason` on `AsrApiException`.
- Hydrate pass2: skip no-retry reasons (J8).
- `open(entry)`: reuse hydrate session (J7); Korean timeout sticky (J6).
- `_wantTranslate` under hydrate: no auth_status (J10).

---

## 4. Out of scope

- Removing single figure net gate / parallel PNG fan-out  
- Bulk figure pull on `/open` (129)  
- CDN / signed GCS URLs  
- Changing reader window UI  

---

## 5. Tests

| # | Assert |
|---|--------|
| T1 | Cold disk (no session) + mocked refresh → PNG 200 |
| T2 | GCS pull fail → 404, no leftover serve |
| T3 | `figure_png_bytes` does not call data-URL path for happy path |
| T4 | Floor + version pin **0.3.164** |
| T5 | Design doc exists with judgments above |

---

## 6. Ship

bump 0.3.164 · deploy `turn2-scale-to-zero` · APK install + GCS upload · retest Co-Ti / 14-figure paper
