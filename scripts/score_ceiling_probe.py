"""design/378 - what does a perfectly correct reading actually score?

A reader's careful takes average 0.78 against a line of 0.60, and one sound is
worth 0.14 in a seven-sound word. That leaves about a sound and a half between
"read it right" and "failed", which is why a slightly rushed sentence collapses.

The question that decides where to fix it: is the missing 0.22 the reader, or the
measurement? The reference is one Google voice heard by the model; a reader is a
different voice heard by the same model, and the model need not write the same
symbols for both even when the words are identical.

So synthesise the same sentence in other voices. Those readings are correct by
construction -- no transcript, no label, nothing fitted -- and whatever they score
is the ceiling the scoring can reach. design/371's rule that the line must not be
fitted to transcript labels is untouched: there are no labels here.

    python scripts/score_ceiling_probe.py .cache/ev416.jsonl

Paper text is never printed. Sentences are read from the evidence and only their
word counts and overlaps come out.
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

# The reference voice itself is the control: it should score near the top, because
# the reference was built from this voice. Anything much under 1.0 there is the
# harness being wrong, not a finding.
VOICES = [
    ("control_same_voice", "en-US-Neural2-D", None),
    ("same_voice_slower", "en-US-Neural2-D", "0.8"),
    ("other_us_male", "en-US-Neural2-A", None),
    ("other_us_female", "en-US-Neural2-F", None),
    ("other_british", "en-GB-Neural2-B", None),
]


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


def heard_of(text: str, voice: str, rate: str | None) -> list[str]:
    from sentence_reading.llm.hear_waveform import phone_frames

    body = escape(text)
    ssml = (f"<speak><prosody rate='{rate}'>{body}</prosody></speak>"
            if rate else f"<speak>{body}</speak>")
    raw, _times = sr.synth_marked(ssml, voice)
    pcm, _rate = sr.pcm_of(raw)
    return [str(one["sym"]) for one in phone_frames(pcm)]


def main() -> int:
    src = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".cache/ev416.jsonl")
    takes = [
        r
        for r in rows(src)
        if r.get("kind") == "practice_skill_align"
        and (r.get("details") or {}).get("phase") == "align"
    ]
    lines: list[str] = []
    seen = set()
    for r in takes:
        text = str((r.get("details") or {}).get("spoken_line") or "").strip()
        if text and text not in seen:
            seen.add(text)
            lines.append(text)
    print(f"{len(lines)} sentences from {src}")

    out: dict[str, list[float]] = {name: [] for name, _v, _r in VOICES}
    for i, text in enumerate(lines, 1):
        got = sr.reference_for(text)
        if not got:
            print(f"  sentence {i}: no reference, skipped")
            continue
        words = [str(w.get("sounds") or "") for w in (got.get("words") or [])]
        askable = [w for w in words if len(split_phone_units(w)) >= MIN_UNITS]
        print(f"  sentence {i}: {len(words)} words, {len(askable)} askable")
        for name, voice, rate in VOICES:
            try:
                heard = heard_of(text, voice, rate)
            except Exception as exc:  # noqa: BLE001
                print(f"      {name}: {type(exc).__name__}")
                continue
            scores = [
                best_window_overlap(split_phone_units(w), heard) for w in askable
            ]
            out[name].extend(scores)
            print(f"      {name}: {len(heard)} sounds heard,"
                  f" mean overlap {stat.mean(scores):.3f}")

    print()
    print("== the ceiling: a reading that is correct by construction")
    print("voice                words   mean   median    >=0.603   >=0.72")
    for name, _v, _r in VOICES:
        got = out[name]
        if not got:
            continue
        a = sum(1 for s in got if s >= 0.603) / len(got)
        b = sum(1 for s in got if s >= 0.72) / len(got)
        print(f"{name:<20} {len(got):5d}  {stat.mean(got):.3f}  "
              f"{stat.median(got):.3f}    {a:.0%}       {b:.0%}")

    print()
    print("For comparison, from the live log: this reader's careful takes averaged")
    print("0.78 and the line they were judged by was 0.603.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
