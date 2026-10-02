"""design/378 - is the ceiling the same for every word, or does each word have one?

The ceiling run showed a reading that is correct by construction averaging 0.84 and
still failing 7% of words. If that 7% is scattered at random the scoring is simply
noisy. If instead particular words have a low ceiling of their own, then judging
them by the same line as every other word is the error, and dividing each word's
score by its own ceiling would fix those words without touching the rest.

This asks both: each word's ceiling, and whether the words the reader failed are the
ones with low ceilings.

    python scripts/ceiling_per_word_probe.py .cache/ev416.jsonl 5

Paper text is never printed beyond the printed word itself, which `slot_pieces`
already puts in the evidence stream.
"""

from __future__ import annotations

import json
import pathlib
import statistics as stat
import sys
from xml.sax.saxutils import escape

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from sentence_reading.llm import sound_reference as sr  # noqa: E402
from sentence_reading.llm.phone_match import (  # noqa: E402
    best_window_overlap,
    split_phone_units,
)

MIN_UNITS = 3
REF_VOICE = "en-US-Neural2-D"


def rows(path: pathlib.Path) -> list[dict]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def heard_of(text: str, voice: str) -> list[str]:
    from sentence_reading.llm.hear_waveform import phone_frames

    raw, _t = sr.synth_marked(f"<speak>{escape(text)}</speak>", voice)
    pcm, _rate = sr.pcm_of(raw)
    # design/379 - cut it the way the reference and the reader are cut. Leaving
    # the model's own grouping in place put oʊ against o + ʊ and counted
    # every diphthong in the sentence as a mistake, which is where this probe
    # first reported a ceiling of 0.82 instead of 1.000.
    return split_phone_units(" ".join(str(one["sym"]) for one in phone_frames(pcm)))


def main() -> int:
    src = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".cache/ev416.jsonl")
    want = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    takes = [
        r
        for r in rows(src)
        if r.get("kind") == "practice_skill_align"
        and (r.get("details") or {}).get("phase") == "align"
    ]
    takes.sort(key=lambda r: str(r.get("ts") or ""))
    d = takes[want - 1].get("details") or {}

    text = str(d.get("spoken_line") or "").strip()
    words = [w.strip() for w in str(d.get("slot_pieces") or "").split("|")]
    refs = [w.strip() for w in str(d.get("target_phones") or "").split("|")]
    user_heard = split_phone_units(str(d.get("heard_phones") or ""))
    line = (d.get("line_used") or 0) / 1000

    native = heard_of(text, REF_VOICE)
    print(f"line {line:.3f}   native run {len(native)} sounds,"
          f" reader's run {len(user_heard)} sounds")
    print()
    print("word                sounds  ceiling  reader   reader/ceiling  verdict")
    rowsout = []
    for w, ref in zip(words, refs):
        units = split_phone_units(ref)
        if len(units) < MIN_UNITS:
            continue
        ceil = best_window_overlap(units, native)
        mine = best_window_overlap(units, user_heard)
        share = mine / ceil if ceil > 0 else 0.0
        verdict = "pass" if mine >= line else "FAIL"
        rowsout.append((w, len(units), ceil, mine, share, verdict))
        print(f"{w[:18]:<18}  {len(units):5d}   {ceil:.3f}   {mine:.3f}"
              f"      {share:.3f}       {verdict}")

    ceils = [r[2] for r in rowsout]
    print()
    print(f"ceilings: mean {stat.mean(ceils):.3f}, lowest {min(ceils):.3f},"
          f" highest {max(ceils):.3f}")
    low = [r for r in rowsout if r[2] < line]
    print(f"words whose ceiling is under the line: {len(low)} of {len(rowsout)}")
    for r in low:
        print(f"   {r[0][:18]:<18} ceiling {r[2]:.3f} -- cannot pass however read")

    # Does the ratio separate the half that was read from the half that was not,
    # better than the raw score does? Front and back by position.
    half = len(rowsout) // 2
    for name, idx in (("raw score", 3), ("score / ceiling", 4)):
        front = [r[idx] for r in rowsout[:half]]
        back = [r[idx] for r in rowsout[half:]]
        print()
        print(f"{name}: front {stat.mean(front):.3f}  back {stat.mean(back):.3f}"
              f"  gap {stat.mean(front) - stat.mean(back):+.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
