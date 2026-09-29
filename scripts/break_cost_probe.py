"""A 1ms break returns every word end. What does it cost the pronunciation?

Marks alone cannot give a word's end, because a mark reports where the audio after
it begins. A `break` between the closing and opening marks fixes that and all the
ends come back, but the audio is no longer byte identical and the symbol run
differs, so the question is which kind of difference it is.

Two kinds, and only one of them matters.

  Harmless  - the voice says the same sounds and merely leaves more room between
              words. Wider gaps would help: the tiling would have room to work and
              every word end would be known exactly.
  Fatal     - the voice changes how it says the words, the way it does when a word
              is synthesised on its own: `at` becomes `a d` instead of `ae t`. Then
              the reference is not the reading the learner is copying.

So the two symbol runs are lined up word by word. Same sounds per word means
harmless. Different sounds per word means fatal.
"""
from __future__ import annotations

import json
import pathlib
import statistics as stat
import sys
import unicodedata

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from ctc_reference_probe import pcm_from_wav  # noqa: E402
from cross_voice_probe import REF_VOICE, synth_voice  # noqa: E402
from mark_in_space_probe import SENTENCES, build  # noqa: E402

import importlib  # noqa: E402

wide = importlib.import_module("timing_spread_probe")


def nm(u: str) -> str:
    return "-".join(unicodedata.name(c, "U%04X" % ord(c)).split()[-1] for c in u)


def main() -> int:
    m = wide.M()
    out, rows = [], []
    for si, sent in enumerate(SENTENCES):
        got = {}
        for kind in ("plain", "b1"):
            ssml, words = build(sent, kind)
            raw, times = synth_voice(ssml, REF_VOICE)
            pcm, rate = pcm_from_wav(raw)
            heard = m.run(pcm, rate)
            got[kind] = {"words": words, "times": times, "heard": heard,
                         "rate": rate, "seconds": len(pcm) / rate}
        words = got["plain"]["words"]

        # Same window rule on both, so only the speech can differ.
        def per_word(g):
            per = []
            for i, _w in enumerate(words):
                lo = g["times"][f"w{i}"] - 0.025
                hi = g["times"].get(f"w{i + 1}", g["seconds"]) + 0.025
                per.append([
                    s["sym"] for s in g["heard"]
                    if lo <= (m.s(s["f0"], g["rate"]) + m.s(s["f1"], g["rate"])) / 2 < hi
                ])
            return per

        a, b = per_word(got["plain"]), per_word(got["b1"])
        out.append(f"sentence {si}: {sent}")
        out.append(f"  plain {got['plain']['seconds']:.2f}s, "
                   f"b1 {got['b1']['seconds']:.2f}s")
        same = 0
        for i, word in enumerate(words):
            mark = "same" if a[i] == b[i] else "DIFFERENT"
            same += a[i] == b[i]
            out.append(f"  {word:<10}{mark:<10} plain: {' '.join(nm(x) for x in a[i])}")
            out.append(f"  {'':<10}{'':<10}    b1: {' '.join(nm(x) for x in b[i])}")
            rows.append({"sentence": si, "word": word,
                         "plain": " ".join(a[i]), "b1": " ".join(b[i]),
                         "same": a[i] == b[i]})
        # The gap a break buys, measured the only way available: between the
        # last sound inside one word's window and the first inside the next.
        gaps = {}
        for kind, g in got.items():
            per = a if kind == "plain" else b
            widths = []
            for i in range(len(words) - 1):
                widths.append(
                    (g["times"][f"w{i + 1}"] - g["times"][f"w{i}"]) * 1000
                )
            gaps[kind] = stat.mean(widths)
        out.append(f"  words matching: {same}/{len(words)}   "
                   f"mark spacing plain {gaps['plain']:.0f}ms "
                   f"b1 {gaps['b1']:.0f}ms")
        out.append("")
        print(f"sentence {si}: {same}/{len(words)} words unchanged, "
              f"{got['plain']['seconds']:.2f}s -> {got['b1']['seconds']:.2f}s, "
              f"mark spacing {gaps['plain']:.0f} -> {gaps['b1']:.0f}ms")

    total = len(rows)
    kept = sum(1 for r in rows if r["same"])
    print(f"\nwords the break left alone: {kept}/{total}")
    pathlib.Path(".cache/break_cost.txt").write_text(
        "\n".join(out), encoding="utf-8"
    )
    pathlib.Path(".cache/break_cost_report.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print("wrote .cache/break_cost.txt and .cache/break_cost_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
