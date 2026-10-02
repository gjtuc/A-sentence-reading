"""design/382 - soft matches over the longer of the two sides.

The owner's formula: every reference sound is worth up to 1, earned by how well it
was pronounced, and the divisor is the longer of the reference and what the reader
actually said. A reader who says every reference sound and then one more scores
3/4, not 3/3.

That is the shipped rule's divisor with design/381's numerator, so it replaces two
separate parts at once -- the floor on the least certain sound, and counting the
sounds the reader added. This measures whether it does.

The reference words are still cut by Google's marks (design/371). The frame times
are used only to sort the reader's sounds into those mark-decided windows, which is
the allowed direction.

Usage:
    python scripts/symmetric_score_probe.py
"""
from __future__ import annotations

import pathlib
import statistics as stat
import sys
from xml.sax.saxutils import escape

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

CASES = [
    ("The light passes through the water without loss.", "loss", "lost"),
    ("The single cell performance was stable for one hundred hours.",
     "stable", "table"),
    ("The catalyst was prepared by chemical vapor deposition.",
     "prepared", "repaired"),
    ("Nanoparticles were dispersed on the carbon support.",
     "dispersed", "disperse"),
    ("We measured the surface area after cycling.", "measured", "treasured"),
]


def sheet_of(text: str, voice: str):
    """The probability sheet for one reading, the eSpeak-free way."""
    import torch

    from sentence_reading.llm import hear_waveform as hw
    from sentence_reading.llm import sound_reference as sr

    raw, _t = sr.synth_marked(f"<speak>{escape(text)}</speak>", voice)
    pcm, rate = sr.pcm_of(raw)
    hw._load_frames()
    hw._load_ctc()
    with hw._LOCK:
        values = hw._EXTRACTOR(
            pcm, sampling_rate=rate, return_tensors="pt"
        ).input_values
        with torch.no_grad():
            logits = hw._MODEL(values).logits
    return torch.log_softmax(logits, dim=-1)[0]


def said_in(rows: list[list[float]], lo: int, hi: int, pad: int) -> list[int]:
    """What the model freely reads off the audio between two frames.

    Collapse-repeats-and-drop-blanks, which is CTC's own answer to "how many
    sounds are in here". The whole vocabulary is in play on purpose: a sound the
    reference does not contain is exactly the sound this is looking for.
    """
    out: list[int] = []
    last = -1
    for t in range(max(0, lo), min(len(rows), hi + 1)):
        row = rows[t]
        top = max(range(len(row)), key=row.__getitem__)
        if top != last and top != pad:
            out.append(top)
        last = top
    return out


def main() -> int:
    import math

    from sentence_reading.llm import hear_waveform as hw
    from sentence_reading.llm import sound_reference as sr

    voice = sr.reference_voice()
    hw._load_frames()
    ids = {sym: tid for tid, sym in hw._INV.items()}
    print(f"voice {voice}   vocabulary {len(ids)}")

    def measure(text: str, groups: list[list[str]]):
        """Per word, from the shipped function -- not a copy of it.

        A probe that reimplements the thing it is measuring can agree with itself
        while the product does something else.
        """
        got = hw.sound_score_of(sheet_of(text, voice), groups)
        if got is None:
            return None
        out = []
        for i, one in enumerate(got):
            if one is None:
                out.append(None)
                continue
            out.append({
                "mean": one["sure"],
                "low": one["low"],
                "sym": one["sym"],
                "hard": one["n"] / max(one["n"], one["said"]),
                "n": int(one["n"]),
                "said": int(one["said"]),
                "each": [],
            })
        return out

    print()
    print("                          read it                    read it wrong")
    print("                          mean   owner  shipped      mean   owner  shipped")
    rows_out = []
    others = {"mean": [], "sym": [], "hard": []}
    others_wrong = {"mean": [], "sym": [], "hard": []}
    for text, word, swap in CASES:
        ref = sr.reference_for(text, allow_build=True)
        if not ref:
            print(f"  no reference for {text[:40]}")
            continue
        groups = [str((w or {}).get("sounds") or "").split()
                  for w in (ref.get("words") or [])]
        printed = text.rstrip(".").split()
        try:
            idx = printed.index(word)
        except ValueError:
            print(f"  {word} not in {text[:30]}")
            continue
        good = measure(text, groups)
        bad = measure(text.replace(word, swap), groups)
        if good is None or bad is None or not good[idx] or not bad[idx]:
            print(f"  {word} could not be asked about")
            continue
        g, b = good[idx], bad[idx]
        print(f"{word:11s}-> {swap:11s}  {g['mean']:.3f}  {g['sym']:.3f}  "
              f"{g['hard']:.3f}        {b['mean']:.3f}  {b['sym']:.3f}  "
              f"{b['hard']:.3f}")
        print(f"{'':11s}   sounds {g['n']:2d}   said {g['said']:2d} right, "
              f"{b['said']:2d} wrong")
        rows_out.append((g, b))
        for i, (x, y) in enumerate(zip(good, bad)):
            if i != idx and x and y:
                for key in others:
                    others[key].append(x[key])
                    others_wrong[key].append(y[key])

    if not rows_out:
        return 1
    print()
    for key, label in (("mean", "mean certainty (design/381)"),
                       ("sym", "owner's symmetric score"),
                       ("hard", "the divisor alone, nothing else")):
        right = [g[key] for g, _b in rows_out]
        wrong = [b[key] for _g, b in rows_out]
        split = min(right) > max(wrong)
        print(f"{label:40s} right {stat.mean(right):.3f} (lowest "
              f"{min(right):.3f})  wrong {stat.mean(wrong):.3f} (highest "
              f"{max(wrong):.3f})  one line splits all: {split}")
    print()
    print("the words nobody touched -- a divisor that punishes sounds the model")
    print("imagines would show up here, on readings that are correct:")
    for key, label in (("mean", "mean certainty"), ("sym", "owner's score"),
                       ("hard", "the divisor alone")):
        vals = others[key]
        under = sum(1 for v in vals if v < 0.603)
        print(f"  {label:16s} {stat.mean(vals):.3f}   under the live line 0.603: "
              f"{under}/{len(vals)}")
    print()
    print("same words, in the reading with one word swapped (should barely move):")
    for key, label in (("mean", "mean certainty"), ("sym", "owner's score")):
        print(f"  {label:16s} {stat.mean(others_wrong[key]):.3f}")
    assert math.isfinite(stat.mean(others["sym"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
