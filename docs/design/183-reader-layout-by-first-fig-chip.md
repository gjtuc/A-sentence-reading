# 183 — Reader layout by first Fig/Table chip (Intro collapse)

**Status:** SHIPPED (mobile · 0.3.174)  
**Parents:** [28](28-fig-ref-jump.md) · [97](97-reader-panel-expand.md) · [98](98-reader-split-drag.md) · [135](135-cover-as-figure.md) · [139](139-fig-ref-chip-formal.md) · [148](148-mobile-cite-ref-panel.md) · [156](156-reader-vertical-panel-swipe.md) · [157](157-this-paper-panel.md)

**Trigger:** Intro에서 cite+figure 패널에 문장이 깔림 → Title만 cover 스플릿, 첫 matched Fig/Table 칩 문장 `T` 이전은 문장 전체화면, `T` 이상(및 그 경계 양방향)은 기본 스플릿. 수동 복귀 허용. cite 패널 로컬 접기.

---

## 0. Success

| Pass | Fail |
|------|------|
| `i < T` → 기본 `sentenceOnly` | Intro에서 그림 패널이 기본으로 공간을 먹음 |
| `i >= T` → 기본 `split` 0.6 | 첫 칩 문장 진입 후에도 접힌 채 |
| `T-1 ↔ T` 양방향(±1·점프·wrap) | 피커 점프 시 레이아웃 안 바뀜 |
| Title+cover → split (cover 있을 때) | cover 없는데 빈 그림 프레임 |
| 사용자 더블탭/스플릿/156 → pin, auto 덮지 않음 | 한 칸 이동마다 수동 레이아웃 리셋 |
| cite 헤더로 접기/펴기 (설정 토글과 별개) | 설정 OFF와 동일 플래그 |
| 칩 탭 = figure_index만 (+ 접혀 있으면 split으로 보이게) | 칩이 sentence_index 변경 |
| `hintsForSentence`와 동일 T | unmatched `Fig. 99` / cite 숫자로 T 설정 |

---

## 1. Locked judgments

| # | Judgment |
|---|----------|
| J1 | `T = min i` where `hintsForSentence(sentences[i], figures, supplementaryMerged)` non-empty; else `null` |
| J2 | SoT for T at runtime = **client recompute** (matches visible chips); server field is cache/open hint |
| J3 | Auto desire: Title∧cover → `split`; else `T==null` or `i<T` → `sentenceOnly`; else `split` |
| J4 | Auto never sets `figureOnly`; user 156/더블탭 figure = **pin** |
| J5 | User layout gesture (더블탭·스플릿바·156) → `userPinned` until paper change |
| J6 | Chip tap: `goToFigureIndex` only; if `sentenceOnly` → `split` + **pin** |
| J7 | Cite collapse is **local** to reader session; default collapsed; not synced to T; settings `enabled` unchanged |
| J8 | Kill `ASR_READER_LAYOUT_AUTO=0` → legacy always-split on paper open; no auto desire |
| J9 | Kill `ASR_FIG_REF_HINTS=0` → also disable auto layout (chips invisible) |
| J10 | `figure_index` not auto-synced to sentence (28); Title does not force cover index in v1 |
| J11 | Web follow later; mobile 0.3.173 |

---

## 2. Crossing ≡ desireFor(i)

Implement as **recompute desire on every real sentence index change + paper open** (not only ±1 edge). Equivalent to expand/collapse rules for jumps/wrap/restore.

```text
onSentenceIndexChanged(from, to) / applyInitial(i):
  if !autoEnabled || mode==userPinned: return
  applyDesire(desireFor(to))
```

---

## 3. Implementation map

| Piece | Location |
|-------|----------|
| `first_fig_table_chip_sentence_index` | `fig_refs.py` + Dart `fig_refs.dart` / threshold helper |
| session/open field | `paper_cache.save` + `/open` compute |
| Policy | `mobile/lib/api/reader_layout_policy.dart` |
| Wire | `library_controller` callback · `reader_screen` |
| Cite UI | collapse header around `_CiteRefPanel` |
| Status | `reader_layout_auto` |

---

## 4. Implementation hazards (필독)

See conversation lock + abbreviated:

1. T must use **matched** chips only (same as `_figRefChipRow`)
2. All sentence moves via library callback (picker/bookmark/wrap)
3. Pin vs auto; never pin on auto applyDesire
4. paint armed → no layout animation/mode change
5. `_ensureLayoutForSession` must apply desire, not blind split
6. Do not use cite chips or section name "Results" as T
7. SI merge / reanalyze → recompute T
8. Version bump four files; deploy guard; evidence kind add-only if used

---

## 5. Tests

- Py/Dart: T=5, unmatched, cite-only, null, T=0, SI
- Policy: desireFor matrix + pin blocks
- Manual: Intro collapse, cross T, jump, chip tap, pin, cite toggle

---

## 6. Version

**0.3.173** · kill `ASR_READER_LAYOUT_AUTO`
