"""Use the broken-up reading as a template to pick each word out of the natural one.

Two recordings of the same sentence exist at analysis time. The broken-up one cuts
into correct words but is not the reading the learner copies. The natural one is
that reading but its words run into each other: `small` comes out
`z s m oo l ae`, carrying the `z` off `is` and the `ae` off `at`.

Neither is what scoring wants. What scoring wants is the natural reading's sounds
for exactly one word. The broken-up reading says which sounds those are, so it can
serve as a template: line the clean words up against the natural run in order, and
each natural sound lands on the word it belongs to.

    clean    s m oo l
    natural  ... i z | s m oo l | ae t ...
    picked           s m oo l          from the natural recording

This does not need a model to be asked what a word sounds like. Nothing is
invented; sounds already in the natural recording are handed out. Asking a model
to produce the symbols would put a dictionary back in the middle of the scorer,
which is what design/368 took out: a dictionary says what the word should sound
like, and the reference has to say what this voice did.

Lining two sequences up in order is a dynamic program, so it is exact, free, and
testable. Compared against the two builds it sits between, on sounds read by hand
off this voice and on the one-word-wrong set at matched pass lines.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import unicodedata

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from sentence_reading.llm.phone_match import (  # noqa: E402
    _MIN_PHONES,
    best_window_overlap,
    split_phone_units,
)
from ctc_reference_probe import pcm_from_wav, ssml_with_marks  # noqa: E402
from cross_voice_probe import READ_VOICE, REF_VOICE, synth_voice  # noqa: E402
from halfgap_tile_probe import hand_out  # noqa: E402
from mark_boundary_probe import TRUTH  # noqa: E402
from one_word_wrong_probe import SWAPS  # noqa: E402
from two_voices_probe import cut_flat, cut_own, ssml_broken  # noqa: E402

import importlib  # noqa: E402

wide = importlib.import_module("timing_spread_probe")

BREAK = 100
PAD = 25
LINES = [0.72, 0.78, 0.82, 0.85, 0.88, 0.90]


def units(syms) -> list[str]:
    return split_phone_units(" ".join(syms))


def nm(u: str) -> str:
    return "-".join(unicodedata.name(c, "U%04X" % ord(c)).split()[-1] for c in u)


def main() -> int:
    m = wide.M()

    builds: dict[str, dict] = {"natural": {}, "clean": {}, "picked": {}}
    dump = []
    for sent in SWAPS:
        # the reading the learner copies
        ssml, words = ssml_with_marks(sent)
        raw, times = synth_voice(ssml, REF_VOICE)
        pcm, rate = pcm_from_wav(raw)
        heard = m.run(pcm, rate)
        natural_run = units([s["sym"] for s in heard])
        builds["natural"][sent] = [
            (w, units(s)) for w, s in cut_flat(
                m, heard, words, times, rate, len(pcm) / rate)
        ]

        # the broken-up reading, cut at each word's own marks
        ssml2, words2 = ssml_broken(sent, BREAK)
        raw2, times2 = synth_voice(ssml2, REF_VOICE)
        pcm2, rate2 = pcm_from_wav(raw2)
        clean = [
            (w, units(s)) for w, s in cut_own(
                m, m.run(pcm2, rate2), words2, times2, rate2, PAD,
                len(pcm2) / rate2)
        ]
        builds["clean"][sent] = clean

        # the clean words used as templates over the natural run
        given = hand_out([u for _w, u in clean], natural_run)
        builds["picked"][sent] = [
            (w, given[i]) for i, (w, _u) in enumerate(clean)
        ]

        if sent == "This effect is small at room temperature.":
            dump.append(sent)
            for i, (w, cu) in enumerate(clean):
                nu = builds["natural"][sent][i][1]
                pu = builds["picked"][sent][i][1]
                dump.append(f"  {w}")
                dump.append(f"    natural {len(nu)}  {' '.join(nm(x) for x in nu)}")
                dump.append(f"    clean   {len(cu)}  {' '.join(nm(x) for x in cu)}")
                dump.append(f"    picked  {len(pu)}  {' '.join(nm(x) for x in pu)}")
        print(f"built {sent[:44]}")

    reads = {}
    for sent, pairs in SWAPS.items():
        for target, wrong in pairs:
            said = re.sub(rf"\b{target}\b", wrong, sent, count=1)
            raw, _t = synth_voice(f"<speak>{said}</speak>", READ_VOICE)
            pcm, rate = pcm_from_wav(raw)
            reads[(sent, target)] = units([s["sym"] for s in m.run(pcm, rate)])

    print("\nagainst sounds read by hand off this voice")
    truth_score = {}
    for name, per in builds.items():
        ok = bad = 0
        misses = []
        for sent, pairs in per.items():
            for w, u in pairs:
                want = TRUTH.get(w)
                if want is None:
                    continue
                want_u = split_phone_units(want)
                if u == want_u:
                    ok += 1
                else:
                    bad += 1
                    misses.append(w)
        truth_score[name] = {"right": ok, "of": ok + bad, "missed": misses}
        print(f"  {name:<9}{ok}/{ok + bad} exactly right"
              + (f"   missed: {', '.join(misses)}" if misses else ""))

    print("\ncaught wrong / kept right, at the same pass line for all three")
    head = "".join(f"{name:>22}" for name in builds)
    print(f"{'line':>6}{head}")
    table = {}
    for line in LINES:
        cells = []
        for name, per in builds.items():
            tgt = keep = hit = kept = 0
            for (sent, target), run in reads.items():
                for word, ref_u in per[sent]:
                    if len(ref_u) < _MIN_PHONES:
                        continue
                    ratio = best_window_overlap(ref_u, run)
                    if word.lower() == target.lower():
                        tgt += 1
                        hit += ratio < line
                    else:
                        keep += 1
                        kept += ratio >= line
            cells.append(f"{hit}/{tgt} {hit / tgt:.0%} keep {kept / keep:.0%}")
            table.setdefault(name, {})[line] = {
                "caught": hit, "targets": tgt, "kept": kept, "keepable": keep}
        print(f"{line:>6.2f}" + "".join(f"{c:>22}" for c in cells))

    judged = {
        name: sum(1 for s in per for _w, u in per[s] if len(u) >= _MIN_PHONES)
        for name, per in builds.items()
    }
    print(f"\nwords judged: " + ", ".join(f"{k} {v}" for k, v in judged.items()))

    pathlib.Path(".cache/clean_template.txt").write_text(
        "\n".join(dump), encoding="utf-8")
    pathlib.Path(".cache/clean_template_report.json").write_text(
        json.dumps({"truth": truth_score, "table": table, "judged": judged,
                    "builds": builds}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print("wrote .cache/clean_template_report.json and .cache/clean_template.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
