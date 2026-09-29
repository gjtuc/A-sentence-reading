"""How much would knowing where the word sits buy us?

The one-word-wrong test says the scorer catches 38% of mispronounced words at the
chosen pad. That is bad, and the pad is not why. `best_window_overlap` looks for
the word's sounds anywhere in the whole take and keeps the best it finds. A three
sound word against a thirty five sound take gets about a hundred and fifty tries,
so it nearly always finds something that fits. The word's place in the sentence,
which the reference already knows, is never used.

Two numbers separate the two things that could be going wrong:

  anywhere  - today's score, best stretch in the whole take
  in place  - best stretch inside the word's own region of the take

The gap between them is what position information is worth. What `in place` still
misses is the model hearing the two words the same, which no amount of alignment
can recover.

The word's region in the take is taken from marks on the take itself. Real takes
have no marks, so this is an upper bound on what aligning the two runs could
reach, which is exactly the number needed to decide whether to build it.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from sentence_reading.llm.phone_match import (  # noqa: E402
    _MIN_PHONES,
    _OVERLAP_MIN,
    best_window_overlap,
    split_phone_units,
)
from ctc_reference_probe import pcm_from_wav, ssml_with_marks  # noqa: E402
from cross_voice_probe import READ_VOICE, REF_VOICE, synth_voice  # noqa: E402
from one_word_wrong_probe import SWAPS  # noqa: E402

import importlib  # noqa: E402

wide = importlib.import_module("timing_spread_probe")

PAD = 25  # the pad the earlier probes settled on, both sides


def cut(m, heard, words, times, rate, pad_ms=PAD):
    pad = pad_ms / 1000.0
    out = []
    for i, word in enumerate(words):
        lo = times[f"w{i}"] - pad
        hi = times.get(f"w{i + 1}", times["end"]) + pad
        # Cut into units the way the live compare does, or the counts differ.
        out.append((word, split_phone_units(" ".join(
            s["sym"] for s in heard
            if lo <= (m.s(s["f0"], rate) + m.s(s["f1"], rate)) / 2 < hi
        ))))
    return out


def main() -> int:
    m = wide.M()

    refs = {}
    for sent in SWAPS:
        ssml, words = ssml_with_marks(sent)
        raw, times = synth_voice(ssml, REF_VOICE)
        pcm, rate = pcm_from_wav(raw)
        refs[sent] = cut(m, m.run(pcm, rate), words, times, rate)
        print(f"ref   {sent[:44]}")

    cases = []
    for sent, pairs in SWAPS.items():
        for target, wrong in pairs:
            said = re.sub(rf"\b{target}\b", wrong, sent, count=1)
            ssml, said_words = ssml_with_marks(said)
            raw, times = synth_voice(ssml, READ_VOICE)
            pcm, rate = pcm_from_wav(raw)
            heard = m.run(pcm, rate)
            whole = split_phone_units(" ".join(s["sym"] for s in heard))
            regions = dict(cut(m, heard, said_words, times, rate))
            cases.append({
                "sentence": sent, "target": target, "wrong": wrong,
                "whole": whole, "regions": regions, "said_words": said_words,
            })
            print(f"read  {said[:56]}")

    print(f"\nthreshold {_OVERLAP_MIN}, floor {_MIN_PHONES}, pad {PAD}ms")
    print(f"\n{'asked':<10}{'said':<10}{'anywhere':>12}{'in place':>12}  verdict")
    score = {"anywhere": {"n": 0, "hit": 0}, "in_place": {"n": 0, "hit": 0}}
    keep = {"anywhere": {"n": 0, "hit": 0}, "in_place": {"n": 0, "hit": 0}}
    rows = []
    for c in cases:
        for word, syms in refs[c["sentence"]]:
            units = syms
            if len(units) < _MIN_PHONES:
                continue
            anywhere = best_window_overlap(units, c["whole"])
            # The take's own slot for this printed word. The swap keeps the word
            # count, so the slot lines up by name for every untouched word and
            # by the replacement for the swapped one.
            want = c["wrong"] if word.lower() == c["target"].lower() else word
            here = c["regions"].get(want) or c["regions"].get(word) or []
            in_place = best_window_overlap(units, here) if here else 0.0
            is_target = word.lower() == c["target"].lower()
            for name, ratio in (("anywhere", anywhere), ("in_place", in_place)):
                bucket = score if is_target else keep
                bucket[name]["n"] += 1
                if is_target:
                    bucket[name]["hit"] += ratio < _OVERLAP_MIN
                else:
                    bucket[name]["hit"] += ratio >= _OVERLAP_MIN
            if is_target:
                v = []
                for ratio in (anywhere, in_place):
                    v.append("caught" if ratio < _OVERLAP_MIN else "missed")
                print(f"{c['target']:<10}{c['wrong']:<10}{anywhere:>12.2f}"
                      f"{in_place:>12.2f}  {v[0]:<7} -> {v[1]}")
            rows.append({
                "slot": word, "swapped": c["target"], "wrong": c["wrong"],
                "units": len(units), "anywhere": round(anywhere, 3),
                "in_place": round(in_place, 3), "is_target": is_target,
            })

    print()
    for name in ("anywhere", "in_place"):
        s, k = score[name], keep[name]
        print(f"{name:<10} caught the wrong word {s['hit']:>3}/{s['n']:<4}"
              f"{s['hit'] / s['n']:>6.0%}   kept the right words "
              f"{k['hit']:>4}/{k['n']:<4}{k['hit'] / k['n']:>6.0%}")

    pathlib.Path(".cache/position_gain_report.json").write_text(
        json.dumps({"rows": rows, "score": score, "keep": keep},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print("\nwrote .cache/position_gain_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
