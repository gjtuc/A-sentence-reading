"""design/379 - which builder cut the live references?

`ref_slice_probe.py` showed that 16 of 24 live references are not slices of the
plain reading of their own sentence, while references built in this checkout are
all 22 of 22. The voice is the same on both sides, and the text reproduces. So the
live ones were cut by a different builder and never rebuilt -- `cache_key` is only
the text and the voice, with no builder version in it, so changing how the cut
works leaves every stored reference alone.

`build` makes two readings. The *stencil* is the mark-and-break reading, where
each word is read with pauses around it, and `hand_out` exists precisely because
a word read that way is not the word read in a sentence: isolated words keep full
vowels and come out longer. The live references are longer. So the question this
asks is simple: are the live references the stencil rather than the handout?

Usage:
    python scripts/ref_vintage_probe.py .cache/ev416.jsonl 5

Counts and printed words only.
"""
from __future__ import annotations

import json
import pathlib
import sys
from xml.sax.saxutils import escape

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from sentence_reading.llm import sound_reference as sr  # noqa: E402
from sentence_reading.llm.phone_match import (  # noqa: E402
    overlap_ratio,
    split_phone_units,
)

MIN_UNITS = 3


def rows(path: pathlib.Path) -> list[dict]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def both_readings(
    text: str, voice: str
) -> tuple[list[str], list[list[str]], list[str]]:
    """The plain reading, and the mark-and-break reading cut into words."""
    from sentence_reading.llm.hear_waveform import phone_frames

    raw, _t = sr.synth_marked(f"<speak>{escape(text)}</speak>", voice)
    pcm, _rate = sr.pcm_of(raw)
    natural = [str(one["sym"]) for one in phone_frames(pcm)]

    ssml, spots = sr.ssml_marked(text)
    marked, times = sr.synth_marked(ssml, voice)
    pcm2, rate2 = sr.pcm_of(marked)
    stencil = sr.cut_marks(
        phone_frames(pcm2), spots, times, len(pcm2) / float(rate2)
    )
    return natural, stencil, [str(one["sym"]) for one in phone_frames(pcm2)]


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
    live = [split_phone_units(w.strip()) for w in str(d.get("target_phones") or "").split("|")]
    voice = sr.reference_voice()

    natural, stencil, marked_run = both_readings(text, voice)
    handout = sr.hand_out(stencil, natural)

    # Index-free, so a token count that differs from the phone's slot count
    # cannot fake the answer. A stencil slice is verbatim in the marked reading;
    # a handout slice is verbatim in the plain one.
    plain_j = " ".join(natural)
    marked_j = " ".join(marked_run)
    in_plain = in_marked = in_neither = asked = 0
    for ref in live:
        if len(ref) < MIN_UNITS:
            continue
        asked += 1
        j = " ".join(ref)
        if j in plain_j:
            in_plain += 1
        elif j in marked_j:
            in_marked += 1
        else:
            in_neither += 1
    print(f"live references verbatim in the plain reading : {in_plain}/{asked}")
    print(f"live references verbatim in the marked reading: {in_marked}/{asked}")
    print(f"live references in neither                    : {in_neither}/{asked}")
    print()

    print(f"take {want}: {len(words)} words, voice {voice}")
    print(f"plain reading {len(natural)} sounds, "
          f"mark-and-break reading cut into {len(stencil)} words")
    print()
    print("word                live  stencil  handout   live~stencil  live~handout")

    tot_sten = tot_hand = n = 0
    exact_sten = exact_hand = 0
    for i, w in enumerate(words):
        if i >= len(live) or len(live[i]) < MIN_UNITS:
            continue
        s = stencil[i] if i < len(stencil) else []
        h = handout[i] if i < len(handout) else []
        a = overlap_ratio(live[i], s) if s else 0.0
        b = overlap_ratio(live[i], h) if h else 0.0
        n += 1
        tot_sten += a
        tot_hand += b
        exact_sten += 1 if live[i] == s else 0
        exact_hand += 1 if live[i] == h else 0
        print(f"{w[:18]:<18}  {len(live[i]):4d}  {len(s):7d}  {len(h):7d}"
              f"   {a:.3f}         {b:.3f}")

    print()
    print(f"live vs the mark-and-break cut : mean {tot_sten / max(n, 1):.3f}, "
          f"exact on {exact_sten}/{n}")
    print(f"live vs the handout            : mean {tot_hand / max(n, 1):.3f}, "
          f"exact on {exact_hand}/{n}")
    print()
    if tot_sten > tot_hand:
        print("VERDICT the live references are the mark-and-break cut. They were built")
        print("        before the handout, and nothing rebuilt them because the cache")
        print("        key has no builder version in it.")
    elif exact_hand == n:
        print("VERDICT the live references are this builder's handout. Look elsewhere.")
    else:
        print("VERDICT neither cut explains them. A third builder, or different text.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
