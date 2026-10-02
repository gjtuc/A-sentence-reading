"""design/379 - what does a different correct reading score, cut correctly?

Matching a reference against the very synthesis it was cut from gives 1.000 for
every word, which proves the reference is sound but says nothing about headroom.
The number that matters is what a *different* correct reading scores: another
native voice, or the same voice slower. That is the best a reader could hope for,
and the distance between it and the pass line is the whole margin the scoring has.

design/377 put this at 0.77 to 0.84 and concluded the reader was already at the
ceiling. That run cut the reference into units and left the model's reading
ungrouped, so every diphthong counted against it. This cuts both sides alike.

No transcript labels: every reading here is correct because a synthesiser produced
it from the same text, so design/371's rule is untouched.

Usage:
    python scripts/ceiling_voices_probe.py .cache/ev416.jsonl 5
"""
from __future__ import annotations

import json
import pathlib
import statistics as stat
import sys
from xml.sax.saxutils import escape

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from sentence_reading.llm import sound_reference as sr  # noqa: E402
from sentence_reading.llm.phone_match import (  # noqa: E402
    best_window_overlap,
    split_phone_units,
)

MIN_UNITS = 3

VOICES = [
    ("same voice, same text", "en-US-Neural2-D", None),
    ("same voice, slower", "en-US-Neural2-D", "0.8"),
    ("another US male", "en-US-Neural2-A", None),
    ("a US female", "en-US-Neural2-F", None),
    ("a British voice", "en-GB-Neural2-B", None),
]


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


def reading_of(text: str, voice: str, rate: str | None) -> list[str]:
    """One correct reading, cut into the units the scorer compares."""
    from sentence_reading.llm.hear_waveform import phone_frames

    body = escape(text)
    ssml = (
        f"<speak><prosody rate='{rate}'>{body}</prosody></speak>"
        if rate
        else f"<speak>{body}</speak>"
    )
    raw, _t = sr.synth_marked(ssml, voice)
    pcm, _rate = sr.pcm_of(raw)
    grouped = [str(one["sym"]) for one in phone_frames(pcm)]
    return split_phone_units(" ".join(grouped))


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
    refs = [
        split_phone_units(w.strip())
        for w in str(d.get("target_phones") or "").split("|")
    ]
    refs = [r for r in refs if len(r) >= MIN_UNITS]
    heard = split_phone_units(str(d.get("heard_phones") or ""))
    line = (d.get("line_used") or 0) / 1000

    print(f"take {want}, pass line {line:.3f}, {len(refs)} words asked about")
    print()
    print("reading                 mean   lowest  clears the line  clears 0.72")

    for name, voice, rate in VOICES:
        run = reading_of(text, voice, rate)
        got = [best_window_overlap(ref, run) for ref in refs]
        clear = sum(1 for g in got if g >= line)
        clear72 = sum(1 for g in got if g >= 0.72)
        print(f"{name:22s} {stat.mean(got):.3f}  {min(got):.3f}   "
              f"{clear:2d}/{len(got)} ({100 * clear // len(got):3d}%)"
              f"      {clear72:2d}/{len(got)}")

    mine = [best_window_overlap(ref, heard) for ref in refs]
    print()
    print(f"the reader on this take: mean {stat.mean(mine):.3f}, "
          f"clears the line {sum(1 for g in mine if g >= line)}/{len(mine)}")
    print()
    print("reading: the gap between a different correct reading and the pass line is")
    print("the whole margin the scoring has to work with.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
