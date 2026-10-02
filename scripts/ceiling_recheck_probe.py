"""design/379 - the ceiling, measured with both sides cut the same way.

design/377 reported that a reading correct by construction scores only 0.82, and
that three words in twenty-four had a ceiling under the pass line and so could not
pass however they were read. That measurement was wrong, and this is the check that
shows it.

The model may hand back a whole diphthong as one symbol (`oʊ`) or a sentence as a
run of separate letters. `split_phone_units` exists to cut either shape into
comparable pieces -- it opens a unit at every base letter, so `oʊ` becomes two.
design/377 put the *split* reference against the *unsplit* model output, so every
diphthong in the sentence counted as a mismatch. That is where the missing 0.18
came from, and where `nanoparticles` lost half its sounds.

The live scorer is not affected: `sound_align_probe.py` reproduced 25 of 25 slots
from the log, which only works because the phone cuts both sides alike.

Usage:
    python scripts/ceiling_recheck_probe.py .cache/ev416.jsonl 5
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
    heard = split_phone_units(str(d.get("heard_phones") or ""))
    line = (d.get("line_used") or 0) / 1000

    from sentence_reading.llm.hear_waveform import phone_frames

    voice = sr.reference_voice()
    raw, _t = sr.synth_marked(f"<speak>{escape(text)}</speak>", voice)
    pcm, _rate = sr.pcm_of(raw)
    grouped = [str(one["sym"]) for one in phone_frames(pcm)]
    # The same reading, cut the way the reference and the reader are cut.
    split = split_phone_units(" ".join(grouped))

    print(f"take {want}, line {line:.3f}, voice {voice}")
    print(f"plain reading: {len(grouped)} symbols from the model, "
          f"{len(split)} units after cutting")
    print(f"reader's run : {len(heard)} units")
    print()
    print("word                sounds  ceiling(377 way)  ceiling(same cut)  reader")

    old: list[float] = []
    new: list[float] = []
    mine: list[float] = []
    under_old = under_new = 0
    for w, ref in zip(words, refs):
        units = split_phone_units(ref)
        if len(units) < MIN_UNITS:
            continue
        a = best_window_overlap(units, grouped)
        b = best_window_overlap(units, split)
        m = best_window_overlap(units, heard)
        old.append(a)
        new.append(b)
        mine.append(m)
        under_old += 1 if a < line else 0
        under_new += 1 if b < line else 0
        print(f"{w[:18]:<18}  {len(units):5d}      {a:.3f}             {b:.3f}"
              f"        {m:.3f}")

    print()
    print(f"ceiling, design/377 way (mixed cuts): mean {stat.mean(old):.3f}, "
          f"lowest {min(old):.3f}, under the line {under_old}/{len(old)}")
    print(f"ceiling, both sides cut alike       : mean {stat.mean(new):.3f}, "
          f"lowest {min(new):.3f}, under the line {under_new}/{len(new)}")
    print(f"the reader's own score on this take : mean {stat.mean(mine):.3f}")
    print()
    if stat.mean(new) > stat.mean(old) + 0.05:
        print("VERDICT design/377's ceiling was its own measurement error. The reference")
        print("        was cut into units and the model's reading was not, so every")
        print("        diphthong in the sentence counted against the reader.")
    else:
        print("VERDICT cutting is not the explanation; the ceiling is real.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
