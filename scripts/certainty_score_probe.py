"""design/381 - does scoring by certainty actually separate right from wrong?

The alignment agrees with torchaudio and the sheet now comes out of the one model
pass. This is the question that decides whether any of it is worth shipping: give a
word's reference sounds and a reading, does the certainty go high when the word was
read and low when a different word was read in its place.

Both readings are synthesised from text, so they are correct or wrong by
construction and no transcript label is involved -- design/371's rule holds.

Usage:
    python scripts/certainty_score_probe.py
"""
from __future__ import annotations

import pathlib
import statistics as stat
import sys
from xml.sax.saxutils import escape

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

# Each line with one word to swap for a near neighbour -- the case design/371 said
# the counting rule is structurally blind to.
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


def main() -> int:
    from sentence_reading.llm import hear_waveform as hw
    from sentence_reading.llm import sound_reference as sr

    voice = sr.reference_voice()
    print(f"voice {voice}")
    print()
    print("swapped word               read it            read it wrong      gap")
    print("                           mean / lowest      mean / lowest")

    right_all: list[float] = []
    wrong_all: list[float] = []
    right_low: list[float] = []
    wrong_low: list[float] = []
    others_low_right: list[float] = []
    others_right: list[float] = []
    others_wrong: list[float] = []

    for text, word, swap in CASES:
        ref = sr.reference_for(text, allow_build=True)
        if not ref:
            print(f"  no reference for {text[:40]}")
            continue
        words = ref.get("words") or []
        groups = [str((w or {}).get("sounds") or "").split() for w in words]
        printed = text.rstrip(".").split()
        try:
            idx = printed.index(word)
        except ValueError:
            print(f"  {word} not in {text[:30]}")
            continue

        good = hw.certainty_of(sheet_of(text, voice), groups)
        bad = hw.certainty_of(
            sheet_of(text.replace(word, swap), voice), groups
        )
        if good is None or bad is None:
            print(f"  no certainty for {text[:40]}")
            continue
        if not good[idx] or not bad[idx]:
            print(f"  {word} could not be asked about")
            continue
        a = sum(good[idx]) / len(good[idx])
        b = sum(bad[idx]) / len(bad[idx])
        lo_a, lo_b = min(good[idx]), min(bad[idx])
        right_all.append(a)
        wrong_all.append(b)
        right_low.append(lo_a)
        wrong_low.append(lo_b)
        for i, (x, y) in enumerate(zip(good, bad)):
            if i != idx and x and y:
                others_right.append(sum(x) / len(x))
                others_wrong.append(sum(y) / len(y))
                others_low_right.append(min(x))
        print(f"{word:12s} -> {swap:12s}   {a:.3f} / {lo_a:.4f}   "
              f"{b:.3f} / {lo_b:.4f}   {a - b:+.3f}")

    print()
    if right_all:
        print(f"the swapped word, read right : mean {stat.mean(right_all):.3f}, "
              f"lowest {min(right_all):.3f}")
        print(f"the swapped word, read wrong : mean {stat.mean(wrong_all):.3f}, "
              f"highest {max(wrong_all):.3f}")
        print(f"separation                   : "
              f"{stat.mean(right_all) - stat.mean(wrong_all):+.3f}")
        print(f"a single line on the mean splits every case: "
              f"{min(right_all) > max(wrong_all)}")
        print()
        print(f"lowest sound, read right : mean {stat.mean(right_low):.4f}, "
              f"lowest {min(right_low):.4f}")
        print(f"lowest sound, read wrong : mean {stat.mean(wrong_low):.4f}, "
              f"lowest {min(wrong_low):.4f}")
        for floor in (0.01, 0.002):
            caught = sum(1 for v in wrong_low if v < floor)
            lost = sum(1 for v in right_low if v < floor)
            other = sum(1 for v in others_low_right if v < floor)
            print(f"  a floor at {floor:g}: catches {caught}/{len(wrong_low)} wrong, "
                  f"wrongly marks {lost}/{len(right_low)} right "
                  f"and {other}/{len(others_low_right)} untouched words")
    if others_right:
        print()
        print(f"every other word in the same sentences, unchanged reading: "
              f"{stat.mean(others_right):.3f}")
        print(f"every other word, reading with one word swapped          : "
              f"{stat.mean(others_wrong):.3f}")
        print("those two should be close -- one wrong word must not drag the rest.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
