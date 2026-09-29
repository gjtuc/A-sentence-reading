"""Can the gap between words be had from marks alone? Google says no.

Giving each word half the quiet on either side needs three numbers per word:
where it starts, where it ends, and how long the quiet is. Marks were supposed to
supply all three, which would keep the cut free of the sound basis. So a mark went
before each word and another right after it:

    <mark w0/>The<mark e0/> <mark w1/>light<mark e1/> ...

Sixteen marks asked for on an eight word sentence. Nine came back: every `w`, and
only the last `e`. Google times a mark by its place in the spoken stream, and
between a closing mark and the next opening mark there is nothing spoken, only a
space, so the two collapse into one. A word's end is therefore not a thing the
marks can report. It is only knowable from the sound, either from the waveform or
from the model's own frame times, and that is the basis the cut is meant to avoid.

So the rule cannot be built the clean way. What marks do give is every word's
start, accurate to about 7ms, and that is what the window is placed from.

Run it to see the inventory for yourself. It prints counts and mark names only.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from cross_voice_probe import REF_VOICE, synth_voice  # noqa: E402
from one_word_wrong_probe import SWAPS  # noqa: E402

_WORD = re.compile(r"[A-Za-z']+")


def ssml_both_ends(sentence: str) -> tuple[str, list[str]]:
    """A mark before and after every word."""
    words = _WORD.findall(sentence)
    parts = ["<speak>"]
    for i, word in enumerate(words):
        parts.append(f'<mark name="w{i}"/>{word}<mark name="e{i}"/> ')
    parts.append("</speak>")
    return "".join(parts), words


def main() -> int:
    report = []
    for sent in SWAPS:
        ssml, words = ssml_both_ends(sent)
        _raw, times = synth_voice(ssml, REF_VOICE)
        starts = [i for i in range(len(words)) if f"w{i}" in times]
        ends = [i for i in range(len(words)) if f"e{i}" in times]
        report.append({
            "words": len(words),
            "marks_asked": 2 * len(words),
            "marks_returned": len(times),
            "starts_returned": len(starts),
            "ends_returned": len(ends),
            "ends_which": ends,
        })
        print(f"{len(words):>3} words: asked {2 * len(words):>3} marks, "
              f"got {len(times):>3} - starts {len(starts)}/{len(words)}, "
              f"ends {len(ends)}/{len(words)} {ends}")

    asked = sum(r["marks_asked"] for r in report)
    got = sum(r["marks_returned"] for r in report)
    ends = sum(r["ends_returned"] for r in report)
    words = sum(r["words"] for r in report)
    print(f"\nacross {len(report)} sentences and {words} words: "
          f"asked {asked} marks, got {got}")
    print(f"word starts: {sum(r['starts_returned'] for r in report)}/{words}")
    print(f"word ends:   {ends}/{words}"
          f"  <- only the last mark of each sentence survives")
    print("\nso a word's end time is not available from marks, and the gap "
          "between two words cannot be measured without the sound.")

    pathlib.Path(".cache/mark_only_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print("\nwrote .cache/mark_only_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
