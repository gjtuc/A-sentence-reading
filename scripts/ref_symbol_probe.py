"""design/379 - do the live references and this checkout use the same sounds?

The live references are verbatim in neither of the two readings this builder makes,
and they are consistently longer. Longer is not automatically wrong: the live
reference for `method` has five sounds and this checkout gave it two, and `method`
does have about five. So before blaming either side, find out whether the two sides
are even drawing from the same alphabet.

Symbols are printed as escaped codepoints. A Windows console cannot render IPA, and
nothing here needs to.

Usage:
    python scripts/ref_symbol_probe.py .cache/ev416.jsonl 5
"""
from __future__ import annotations

import collections
import json
import pathlib
import sys
from xml.sax.saxutils import escape

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from sentence_reading.llm import sound_reference as sr  # noqa: E402
from sentence_reading.llm.phone_match import split_phone_units  # noqa: E402


def esc(sym: str) -> str:
    return sym.encode("unicode_escape").decode("ascii")


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
    live: list[str] = []
    for part in str(d.get("target_phones") or "").split("|"):
        live.extend(split_phone_units(part.strip()))
    heard = split_phone_units(str(d.get("heard_phones") or ""))

    from sentence_reading.llm.hear_waveform import phone_frames

    voice = sr.reference_voice()
    raw, _t = sr.synth_marked(f"<speak>{escape(text)}</speak>", voice)
    pcm, _rate = sr.pcm_of(raw)
    plain = [str(one["sym"]) for one in phone_frames(pcm)]

    lc = collections.Counter(live)
    pc = collections.Counter(plain)
    hc = collections.Counter(heard)

    print(f"take {want}, voice {voice}")
    print(f"live reference sounds {len(live)} in {len(lc)} kinds")
    print(f"plain reading sounds  {len(plain)} in {len(pc)} kinds")
    print(f"reader's own sounds   {len(heard)} in {len(hc)} kinds")
    print()

    only_live = sorted(set(lc) - set(pc))
    only_plain = sorted(set(pc) - set(lc))
    print(f"kinds in the live reference but not in the plain reading: {len(only_live)}")
    for s in only_live:
        print(f"    {esc(s):14s} x{lc[s]}")
    print(f"kinds in the plain reading but not in the live reference: {len(only_plain)}")
    for s in only_plain:
        print(f"    {esc(s):14s} x{pc[s]}")
    print()

    # Does the reader's run draw on anything the reference never has? The reader
    # goes through the same model, so a mismatch there would mean two models.
    stray = sorted(set(hc) - set(pc))
    print(f"kinds the reader produced that the plain reading never does: {len(stray)}")
    for s in stray[:12]:
        print(f"    {esc(s):14s} x{hc[s]}")
    print()

    # Length is the other half of the question. Twenty-five words of reference
    # against a reading of the same sentence: how much longer is the reference?
    print(f"total reference length {len(live)} vs plain reading {len(plain)}"
          f"  ({len(live) - len(plain):+d})")
    print("a reference that is the sum of per-word slices of the plain reading can")
    print("only be shorter than it, never longer -- a skip drops sounds, none are added.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
