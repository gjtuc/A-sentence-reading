"""design/379 - why can a word not reach the pass line however it is read?

design/377 measured a ceiling per word by synthesising the sentence again and
scoring the reference against it. Three words in twenty-four came back with a
ceiling under the line: 0.429 for one of them. Something is wrong, but the
measurement cannot say what, so this names the cause.

The cause has to be one of two things, and they want opposite fixes:

  variance   The reference is one slice of one particular utterance. If Google
             says the same sentence differently the second time, the ceiling is
             the distance between two readings and no amount of fixing the
             builder will raise it.

  handout    `hand_out` gave the word the wrong run of sounds. Then the word is
             being judged against part of its neighbour, and the fix is in the
             builder.

The test that separates them: a word's reference *is* a contiguous slice of the
straight reading (`natural[k:j]`). So if the straight reading is reproducible,
every word must score exactly 1.000 against a fresh one -- a wrong slice is still
a slice, and still found. Any shortfall at all is therefore variance, not the
handout. And if the readings are identical and the shortfall is still there, the
window search is at fault.

No transcript labels anywhere, so design/371's rule stands.

Usage:
    python scripts/ceiling_cause_probe.py
    python scripts/ceiling_cause_probe.py --lines 1
"""
from __future__ import annotations

import argparse
import pathlib
import sys
from xml.sax.saxutils import escape

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

LINES = [
    "The catalyst was prepared by chemical vapor deposition.",
    "Nanoparticles were dispersed on the carbon support.",
    "We measured the electrochemical surface area after cycling.",
]


def straight_run(text: str, voice: str) -> tuple[list[str], bytes]:
    """The sound run of the plain reading -- the same call `build` makes."""
    from sentence_reading.llm import sound_reference as sr
    from sentence_reading.llm.hear_waveform import phone_frames

    raw, _times = sr.synth_marked(f"<speak>{escape(text)}</speak>", voice)
    pcm, _rate = sr.pcm_of(raw)
    return [str(one["sym"]) for one in phone_frames(pcm)], raw


def run_gap(a: list[str], b: list[str]) -> float:
    """How far two whole readings are apart, by the scorer's own measure."""
    from sentence_reading.llm.phone_match import overlap_ratio

    return overlap_ratio(a, b)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lines", type=int, default=len(LINES))
    args = ap.parse_args()

    from sentence_reading.llm import sound_reference as sr
    from sentence_reading.llm.phone_match import best_window_overlap

    voice = sr.reference_voice()
    print(f"voice {voice}")

    for line in LINES[: max(1, args.lines)]:
        got = sr.reference_for(line, allow_build=True)
        if not got:
            print(f"  no reference for {line[:40]}")
            continue
        words = got.get("words") or []
        refs = [str((w or {}).get("sounds") or "").split() for w in words]
        printed = line.rstrip(".").split()

        first, raw1 = straight_run(line, voice)
        second, raw2 = straight_run(line, voice)

        same_bytes = raw1 == raw2
        same_run = first == second
        print()
        print(f"  {line[:52]}")
        print(
            f"    audio identical={same_bytes}  sound run identical={same_run}  "
            f"n1={len(first)} n2={len(second)} "
            f"stored_natural_n={got.get('natural_n')}"
        )
        if not same_run:
            print(f"    two readings of the same text agree {run_gap(first, second):.3f}")

        # Is every stored reference actually a contiguous slice of a fresh
        # straight reading? If the reading is reproducible it has to be.
        joined = " ".join(first)
        inside = sum(1 for r in refs if r and " ".join(r) in joined)
        print(f"    references found verbatim in a fresh reading: {inside}/{len(refs)}")

        worst = []
        for i, ref in enumerate(refs):
            if len(ref) < 3:
                continue
            ceil_first = best_window_overlap(ref, first)
            ceil_second = best_window_overlap(ref, second)
            word = printed[i] if i < len(printed) else f"#{i}"
            worst.append((min(ceil_first, ceil_second), word, len(ref), ceil_first, ceil_second))
        worst.sort()
        print("    lowest ceilings (word, sounds, vs reading 1, vs reading 2):")
        for low, word, n, c1, c2 in worst[:5]:
            flag = "  <-- cannot pass 0.603" if low < 0.603 else ""
            print(f"      {word:18s} {n:2d} sounds  {c1:.3f}  {c2:.3f}{flag}")

    print()
    print("reading: a ceiling under 1.000 against the very reading the reference")
    print("was cut from means the two readings differ, not that the handout erred.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
