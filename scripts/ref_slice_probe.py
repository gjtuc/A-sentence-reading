"""design/379 - is the live reference a slice of the sentence it belongs to?

A reference word's sounds are cut straight out of the plain reading of the whole
sentence (`natural[k:j]` in `hand_out`). And the plain reading reproduces exactly
-- byte-identical audio, identical sound run, measured. So a reference built from
this sentence, in this voice, by this builder must appear *verbatim* inside a
fresh reading of that same sentence, and must therefore score 1.000.

design/377 measured 0.818 on average against the live references, with one word at
0.429. Locally built references score 1.000. So the live references are not slices
of this sentence's reading, and this says which of the three ways that can happen:

    text     the server built from a different string than the log shows
    voice    the server built in a different voice
    builder  the server's cut differs from this checkout's

Usage:
    python scripts/ref_slice_probe.py .cache/ev416.jsonl 5

Prints counts, lengths and the printed word only. No IPA and no paper text beyond
the words `slot_pieces` already carries.
"""
from __future__ import annotations

import json
import pathlib
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


def native_of(text: str, voice: str) -> list[str]:
    from sentence_reading.llm.hear_waveform import phone_frames

    raw, _t = sr.synth_marked(f"<speak>{escape(text)}</speak>", voice)
    pcm, _rate = sr.pcm_of(raw)
    return [str(one["sym"]) for one in phone_frames(pcm)]


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
    live = [w.strip() for w in str(d.get("target_phones") or "").split("|")]
    voice = sr.reference_voice()

    print(f"take {want}: {len(words)} printed words, {len(live)} live references")
    print(f"spoken_line length {len(text)} chars, voice for the retry {voice}")

    native = native_of(text, voice)
    joined = " ".join(native)
    print(f"fresh plain reading: {len(native)} sounds")

    # 1. The live reference as the server stored it.
    verbatim = 0
    total = 0
    worst: list[tuple[float, str, int, bool]] = []
    for w, ref in zip(words, live):
        units = split_phone_units(ref)
        if len(units) < MIN_UNITS:
            continue
        total += 1
        found = " ".join(units) in joined
        verbatim += 1 if found else 0
        worst.append((best_window_overlap(units, native), w, len(units), found))
    print(f"live references found verbatim in that reading: {verbatim}/{total}")

    # 2. The same sentence built here, now.
    mine = sr.reference_for(text, allow_build=True)
    mine_words = (mine or {}).get("words") or []
    mine_refs = [str((x or {}).get("sounds") or "").split() for x in mine_words]
    mine_verbatim = sum(
        1 for r in mine_refs if len(r) >= MIN_UNITS and " ".join(r) in joined
    )
    mine_total = sum(1 for r in mine_refs if len(r) >= MIN_UNITS)
    print(
        f"references built here found verbatim: {mine_verbatim}/{mine_total} "
        f"(stored natural_n {(mine or {}).get('natural_n')})"
    )

    # 3. Same word, two builders: how long is each side's reference?
    print()
    print("word                live  here   ceiling(live)  verbatim")
    worst.sort()
    for ceil, w, n, found in worst:
        idx = words.index(w) if w in words else -1
        mine_n = len(mine_refs[idx]) if 0 <= idx < len(mine_refs) else -1
        print(
            f"{w[:18]:<18}  {n:4d}  {mine_n:4d}   {ceil:.3f}"
            f"          {'yes' if found else 'NO'}"
        )

    print()
    if verbatim == total:
        print("VERDICT the live references are slices of this reading -- look at the")
        print("        window search, not the builder.")
    elif mine_verbatim == mine_total:
        print("VERDICT the builder here is consistent and the live references are not.")
        print("        The live ones were cut from a different reading: different text,")
        print("        voice, or an older builder. Compare lengths above.")
    else:
        print("VERDICT neither side is a slice of this reading -- the text differs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
