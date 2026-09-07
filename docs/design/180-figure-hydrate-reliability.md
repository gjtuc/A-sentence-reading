# 180 — Figure hydrate reliability (serialize · per-PNG · miss retry)

**Parent:** [169n](169n-figure-hydrate-library.md) · [129](129-lazy-figure-open.md) · [179](179-false-worker-lost-poll-library-evidence.md)  
**Status:** DESIGN FROZEN → ship **0.3.163**  
**Trigger:** 2026-09-07 library `그림 4장 받지 못함` while GCS had 14/14 PNGs. Evidence: `figures/window` **TimeoutException 90s** under concurrent `hydrate_bg` + `reader_prefetch`; large data-URL windows.

---

## 0. Locked judgments

| # | Judgment |
|---|----------|
| J1 | **One figure network fetch in-flight** app-wide (hydrate and prefetch share one gate). |
| J2 | While `cache_id` is hydrating, **reader_prefetch for that id is skipped** (hydrate owns the bytes). |
| J3 | Library hydrate uses **per-figure PNG GET** (raw `image/png`), not multi-figure data-URL windows. |
| J4 | Hydrate visits **empty indexes only**; after first pass, **one miss-only retry**. |
| J5 | Reader may still use `/figures/window` (span≤1) but through the **same gate**; window timeout **120s**. |
| J6 | Evidence: `figure_png_req` / `figure_png_done` with `elapsed_ms`, `bytes_n`, `index`, `outcome`; hydrate partial includes `failed_n` + sample `fail_i0..fail_i3`. |
| J7 | Add-only floor. |

---

## 1. New API

```
GET /api/cache/papers/{cache_id}/figures/{figure_id}.png
```

- Paid access gate (same as open).
- Returns `image/png` bytes or 404 JSON fail-closed.
- Resolves via same disk/GCS path as `figure_data_url_with_reason` (no path escape).
- Emits `figure_png_done` server-side with `elapsed_ms`, `bytes_n`, `ok`.

---

## 2. Mobile

### 2.1 Gate

`LibraryController` serializes all `fetchFigureWindow` / `fetchFigurePng` through one chain.

### 2.2 Hydrate loop

```
open + disk inject
for index in emptyIndexes:
  gate → GET png → data URL → merge + disk
for index in stillEmpty:   # one retry
  gate → GET png …
finishHydrate
```

No `hydrateCenters(span:1)` multi-figure windows on hydrate path.

### 2.3 Prefetch

If `_hydrateActive.contains(cacheId)` → return immediately.

### 2.4 Timeouts

| call | timeout |
|------|---------|
| figure PNG GET | **120s** |
| figures/window | **120s** (was 90) |

---

## 3. New kinds

```
figure_png_req
figure_png_done
```

---

## 4. Tests

| # | Assert |
|---|--------|
| T1 | `hydrateCenters(span:0)` is `0..n-1` |
| T2 | PNG endpoint 200 bytes / 404 bad id |
| T3 | Floor + dart mirror |
| T4 | Version pin **0.3.163** |

---

## 5. Out of scope

- Changing reader UI layout  
- CDN / signed GCS URLs (raw API proxy is enough this chip)  
- Removing data-URL window entirely for reader  

---

## 6. Ship

bump 0.3.163 · deploy API · build+install APK · upload GCS APK
