"""The pad belongs on one side only, because the lag runs one way.

Every sound the model reports fires late. That has a consequence the flat pad
ignores. A word's own first sound is late, so it falls further inside its own
window, not out of it. A word's own last sound is late too, so it falls out of
the far end into the next word. Padding the end recovers a sound that belongs to
the word. Padding the start can only reach backwards into the previous word and
take a sound that does not.

`light` in "The light passes through the water without loss" shows both halves.
Unpadded it comes out `l aɪ`, missing its own final `t`. Padded 25ms each way it
comes out `ð ə l aɪ t`: the `t` is back, and so is the whole of `The`. The `t` is
why the pad helps and the `ð ə` is why it hurt, and they came from opposite ends.

Scored the way the flat pad was scored: the reference is built from the original
sentence, the reading is the same sentence with one word swapped for a near miss,
and the numbers are how often the swapped word is caught and how often an
untouched word is still kept.
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

# (pad before the word's mark, pad after the next word's mark) in ms
PADS = [
    (0, 0),
    (25, 25),
    (0, 25),
    (0, 40),
    (0, 60),
    (10, 40),
]


def cut(m, heard, words, times, rate, before_ms, after_ms):
    before, after = before_ms / 1000.0, after_ms / 1000.0
    out = []
    for i, word in enumerate(words):
        lo = times[f"w{i}"] - before
        hi = times.get(f"w{i + 1}", times["end"]) + after
        out.append((word, " ".join(
            s["sym"] for s in heard
            if lo <= (m.s(s["f0"], rate) + m.s(s["f1"], rate)) / 2 < hi
        )))
    return out


def main() -> int:
    m = wide.M()

    refs = {}
    for sent in SWAPS:
        ssml, words = ssml_with_marks(sent)
        raw, times = synth_voice(ssml, REF_VOICE)
        pcm, rate = pcm_from_wav(raw)
        heard = m.run(pcm, rate)
        refs[sent] = {
            f"{b}_{a}": cut(m, heard, words, times, rate, b, a) for b, a in PADS
        }
        print(f"ref   {sent[:44]:<44} syms={len(heard)}")

    readings = {}
    for sent, pairs in SWAPS.items():
        for target, wrong in pairs:
            said = re.sub(rf"\b{target}\b", wrong, sent, count=1)
            raw, _t = synth_voice(f"<speak>{said}</speak>", READ_VOICE)
            pcm, rate = pcm_from_wav(raw)
            readings[(sent, target)] = " ".join(
                s["sym"] for s in m.run(pcm, rate)
            )
    print(f"read  {len(readings)} sentences with one word swapped")

    print(f"\nreference {REF_VOICE}, reading {READ_VOICE}, "
          f"threshold {_OVERLAP_MIN}, floor {_MIN_PHONES}")
    print(f"\n{'before':>7}{'after':>6}{'words judged':>14}"
          f"{'caught the wrong word':>24}{'kept the right words':>23}")
    summary, rows = {}, []
    for b, a in PADS:
        key = f"{b}_{a}"
        caught = {"n": 0, "hit": 0}
        kept = {"n": 0, "hit": 0}
        judged_any = sum(
            1 for sent in SWAPS for _w, ph in refs[sent][key]
            if len(split_phone_units(ph)) >= _MIN_PHONES
        )
        for sent, pairs in SWAPS.items():
            for target, wrong in pairs:
                flat = split_phone_units(readings[(sent, target)])
                for word, phone in refs[sent][key]:
                    units = split_phone_units(phone)
                    if len(units) < _MIN_PHONES:
                        continue
                    ratio = best_window_overlap(units, flat)
                    if word.lower() == target.lower():
                        caught["n"] += 1
                        caught["hit"] += ratio < _OVERLAP_MIN
                    else:
                        kept["n"] += 1
                        kept["hit"] += ratio >= _OVERLAP_MIN
                    rows.append({
                        "pad": key, "slot": word, "swapped": target,
                        "wrong": wrong, "units": len(units),
                        "ratio": round(ratio, 3),
                        "is_target": word.lower() == target.lower(),
                    })
        c = caught["hit"] / caught["n"] if caught["n"] else 0.0
        k = kept["hit"] / kept["n"] if kept["n"] else 0.0
        print(f"{b:>7}{a:>6}{judged_any:>14}{caught['hit']:>16}/{caught['n']:<3}"
              f"{c:>5.0%}{kept['hit']:>14}/{kept['n']:<4}{k:>5.0%}")
        summary[key] = {
            "judged": judged_any,
            "caught": f"{caught['hit']}/{caught['n']}", "caught_rate": round(c, 3),
            "kept": f"{kept['hit']}/{kept['n']}", "kept_rate": round(k, 3),
        }

    pathlib.Path(".cache/asym_pad_report.json").write_text(
        json.dumps({"summary": summary, "rows": rows, "refs": refs},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print("\nwrote .cache/asym_pad_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
