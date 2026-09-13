# 266 — Progressive practice readiness

Version: **0.3.263** · Status: **locked**  
Amends [82](82-shadowing-practice-loop.md) · [113](113-shadowing-chunk-budget.md) · [119](119-shadowing-chunks-build-failclosed.md)  
Orthogonal to [262](262-documents-mirror.md) phase naming (do not confuse doc ids).

## Problem

Practice boot waits for paper-wide `plan.status == ok`. Preparation is faster than practice, so users sit blocked while later sentences are still building.

## Locked product

1. **Unlock** when ≥1 sentence has non-empty `plan.sentences[sid].chunks`.
2. **`status=ok`** still means *all* sentences complete (113 unchanged).
3. **`status=pending`** = still preparing; not a hard fail if `ready_sentence_n ≥ 1`.
4. **Playable** = plan-row chunks only. Plain EN full-text fallback is **not** playable.
5. After unlock, **ensure continues** in background (join / single-flight).
6. Advance: skip unready sids; if none left **and** ensure still pending → show「다음 문장 준비 중」— do **not** claim paper finished.
7. Persist **honest** `pending` plans to device disk (not only `ok`).
8. Soft-hide abandon (258) and practice cursor (246) unchanged.

## Non-goals

Gemini rebuild · mid-HTTP kill · treating pending as `ok` · Documents 262 · rate bias (267).

## Kill

`ASR_SHADOWING_PRACTICE=0` · revert.

## Tests

- Plan-only chunks empty without row  
- Boot unlock with pending + one ready sid  
- Skip unready; end-of-paper blocked while ensure busy  
