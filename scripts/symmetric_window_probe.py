"""design/382 - re-score the 619 recordings with a window that can see the extra.

`.cache/human_takes.json` counted the reader's sounds between the first and last
frame the reference's own sounds landed on. A sound added *after* the reference ran
out -- `loss` read as `lost` -- falls past that last frame and was never counted.
On synthesised audio widening the window to the next word's first sound turned that
case from invisible to caught.

This runs the same widening over the real recordings, so the owner's symmetric
score can be judged on the count it is actually meant to use.

The reference words are still cut by Google's marks. Frame times only sort the
reader's sounds into those mark-decided windows, which is the allowed direction
(design/371).

    python scripts/symmetric_window_probe.py
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import importlib  # noqa: E402

from sentence_reading.llm.phone_match import (  # noqa: E402
    _MIN_PHONES,
    best_window_overlap,
)
from ctc_prob_score_probe import logprobs, sure_per_word  # noqa: E402

htp = importlib.import_module("human_takes_probe")
wide = importlib.import_module("timing_spread_probe")

OUT = pathlib.Path(".cache/human_takes_wide.json")


def main() -> int:
    cards = htp.sidecars()
    print(f"{len(cards)} takes carry the text they were reading")
    m = wide.M()
    refs = htp.build_refs(m, sorted({c["expected"].strip() for c in cards}))

    # Resume. The model is heavy enough that this run has died halfway before,
    # and re-reading 480 recordings to get back to where it was is wasted time.
    rows = []
    if OUT.exists() and "--fresh" not in sys.argv:
        rows = json.loads(OUT.read_text(encoding="utf-8"))
    done = {r["stem"] for r in rows}
    print(f"resuming with {len(rows)} words from {len(done)} takes")
    clock = time.monotonic()
    for n, card in enumerate(cards, 1):
        sent = card["expected"].strip()
        ref = refs.get(sent) or []
        if not ref or card["stem"] in done:
            continue
        said = {htp.bare(w) for w in (card.get("heard") or "").split()}
        try:
            pcm, rate = htp.pcm_of(m, card["stem"])
            sheet = logprobs(m, pcm, rate)
            heard = m.run(pcm, rate)
        except Exception as exc:  # noqa: BLE001
            print(f"  skip take ({type(exc).__name__}) {card['stem'][:20]}")
            continue
        run = htp.units(s["sym"] for s in heard)
        sure = sure_per_word(m, sheet, [list(u) for _w, u in ref])
        # Where the next word's sounds begin. Past the last word, the recording's
        # own end, because anything after the final reference sound belongs to the
        # final word and nowhere else.
        last_frame = int(sheet.shape[0])
        starts = [None if s is None else s[1] for s in sure]
        for i, (word, raws) in enumerate(ref):
            piece = htp.units(raws)
            if len(piece) < _MIN_PHONES or sure[i] is None:
                continue
            cert, f0, f1, certs = sure[i]
            nxt = next((starts[j] for j in range(i + 1, len(ref))
                        if starts[j] is not None), None)
            wide_f1 = last_frame if nxt is None else max(f1, nxt)
            tight = [s for s in heard if f0 <= (s["f0"] + s["f1"]) / 2 < f1]
            broad = [s for s in heard if f0 <= (s["f0"] + s["f1"]) / 2 < wide_f1]
            rows.append({
                "tier": card["skill_tier"],
                "stem": card["stem"],
                "word": word,
                "n": len(certs),
                "bad": 0 if htp.bare(word) in said else 1,
                "overlap": best_window_overlap(piece, run),
                "sure": cert,
                "worst": min(certs),
                "extra": max(0, len(tight) - len(certs)),
                "extra_wide": max(0, len(broad) - len(certs)),
                "full": cert - max(0, len(tight) - len(certs)) / len(certs),
            })
        del sheet
        if n % 10 == 0 or n == len(cards):
            gone = time.monotonic() - clock
            print(f"  scored {n}/{len(cards)} takes, {len(rows)} words, "
                  f"{gone / n:.2f}s per take")
            OUT.write_text(json.dumps(rows, ensure_ascii=False),
                           encoding="utf-8")
    OUT.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT} with {len(rows)} words")
    return 0


if __name__ == "__main__":
    sys.exit(main())
