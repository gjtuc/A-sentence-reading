"""How wide can the window get before a word stops being judged as itself?

The pad sweep looked like wider is always better: 81 of 83 words judged at 120ms
with the correct reading still passing. That figure is worthless, because the
wrong reading it was tested against was a different sentence. Of course a
reference built from `small at room` fails against another sentence.

The reading this app has to catch is not another sentence. It is this sentence
with one word said wrong. A reference stretched wide enough to hold its
neighbours will pass that, because the neighbours were said correctly, and the
per-word verdict the user reads stops meaning anything.

So the reference is built from the original sentence, and the reading is the same
sentence with one word swapped for a near miss. The swapped word's slot must fail
and every untouched word's slot must still pass. That pair of numbers is what
picks the pad.
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

import importlib  # noqa: E402

wide = importlib.import_module("timing_spread_probe")

PADS = [0, 25, 40, 60, 80, 120]

# sentence -> the near misses a learner could plausibly land on
SWAPS = {
    "The film grew at five hundred degrees.": [
        ("film", "farm"), ("grew", "glue"), ("five", "fine"),
        ("hundred", "hungry"),
    ],
    "The catalyst was prepared by chemical vapour deposition.": [
        ("chemical", "comical"), ("vapour", "paper"),
    ],
    "We measured the dispersion of the nanoparticles in water.": [
        ("water", "waiter"), ("measured", "mixture"),
    ],
    "This effect is small at room temperature.": [
        ("small", "smell"), ("room", "rome"), ("effect", "affect"),
    ],
    "The single cell performance was stable for one hundred hours.": [
        ("stable", "table"), ("single", "signal"),
    ],
    "A thin layer forms on the surface of the gold.": [
        ("thin", "then"), ("gold", "cold"), ("layer", "later"),
    ],
    "Energy is released when the oxide is reduced.": [
        ("released", "relaxed"), ("reduced", "produced"),
    ],
    "The light passes through the water without loss.": [
        ("light", "right"), ("loss", "lost"),
    ],
    "Both peaks shift towards lower energy under pressure.": [
        ("peaks", "beaks"), ("lower", "lawyer"),
    ],
    "Zinc oxide shows strong absorption in the ultraviolet.": [
        ("strong", "string"), ("shows", "choose"),
    ],
}

_WORD = re.compile(r"[A-Za-z']+")


def cut(m, heard, words, times, rate, pad_ms):
    pad = pad_ms / 1000.0
    out = []
    for i, word in enumerate(words):
        lo = times[f"w{i}"] - pad
        hi = times.get(f"w{i + 1}", times["end"]) + pad
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
            pad: cut(m, heard, words, times, rate, pad) for pad in PADS
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
            print(f"read  {said[:56]}")

    print(f"\nreference {REF_VOICE}, reading {READ_VOICE}, "
          f"threshold {_OVERLAP_MIN}, floor {_MIN_PHONES}")
    print(f"\n{'pad':>4}{'judged':>8}{'caught the wrong word':>24}"
          f"{'kept the right words':>23}")
    summary, rows = {}, []
    for pad in PADS:
        caught = {"n": 0, "hit": 0}
        kept = {"n": 0, "hit": 0}
        judged_target = 0
        for sent, pairs in SWAPS.items():
            for target, wrong in pairs:
                flat = split_phone_units(readings[(sent, target)])
                for word, phone in refs[sent][pad]:
                    units = split_phone_units(phone)
                    if len(units) < _MIN_PHONES:
                        continue
                    ratio = best_window_overlap(units, flat)
                    is_target = word.lower() == target.lower()
                    if is_target:
                        judged_target += 1
                        caught["n"] += 1
                        caught["hit"] += ratio < _OVERLAP_MIN
                    else:
                        kept["n"] += 1
                        kept["hit"] += ratio >= _OVERLAP_MIN
                    rows.append({
                        "pad": pad, "sentence": sent[:30], "slot": word,
                        "swapped": target, "wrong": wrong,
                        "units": len(units), "ratio": round(ratio, 3),
                        "is_target": is_target,
                    })
        c = caught["hit"] / caught["n"] if caught["n"] else 0.0
        k = kept["hit"] / kept["n"] if kept["n"] else 0.0
        print(f"{pad:>4}{judged_target:>8}{caught['hit']:>16}/{caught['n']:<3}"
              f"{c:>5.0%}{kept['hit']:>14}/{kept['n']:<4}{k:>5.0%}")
        summary[pad] = {
            "caught_wrong": f"{caught['hit']}/{caught['n']}", "caught_rate": round(c, 3),
            "kept_right": f"{kept['hit']}/{kept['n']}", "kept_rate": round(k, 3),
        }

    pathlib.Path(".cache/one_word_wrong_report.json").write_text(
        json.dumps({"summary": summary, "rows": rows, "refs": {
            s: {str(p): v for p, v in d.items()} for s, d in refs.items()
        }}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print("\nwrote .cache/one_word_wrong_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
