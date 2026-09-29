"""Half the gap to each side, with every number from a mark. The asked-for rule.

A mark reports where the audio after it begins, so a closing mark placed right
after a word simply repeats the next word's start and gets dropped. Putting a
`break` between the two separates them, and then Google returns every word end:
83 of 83 where a bare closing mark returned 10.

The break was nearly free. Mark spacing moved from 256ms to 246ms, so the voice
did not slow down or pause, and 14 of 22 words came out with identical sounds.
Of the 8 that moved, 5 moved the right way: `small` went from `z s oo l ae`, which
carried the `z` off `is` and the `ae` off `at`, to exactly `s m oo l`. The break
cost some neighbour bleed, which is the thing the pad was there to tolerate.

So the rule can now be built with no sound times anywhere:

    start_i  = mark w_i
    end_i    = mark e_i
    gap_i    = mark w_(i+1) - mark e_i
    window_i = [ start_i - gap_(i-1)/2 , end_i + gap_i/2 ]

The windows tile the sentence: no overlap, no leftovers, no constant to tune.
Scored against the flat 25ms pad on the same one-word-wrong set, and compared at
matched specificity, because the two put their scores on different scales.
"""
from __future__ import annotations

import json
import pathlib
import re
import statistics as stat
import sys
import unicodedata

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from sentence_reading.llm.phone_match import (  # noqa: E402
    _MIN_PHONES,
    _OVERLAP_MIN,
    best_window_overlap,
    split_phone_units,
)
from ctc_reference_probe import pcm_from_wav, ssml_with_marks  # noqa: E402
from cross_voice_probe import READ_VOICE, REF_VOICE, synth_voice  # noqa: E402
from one_word_wrong_probe import SWAPS  # noqa: E402

import importlib  # noqa: E402

wide = importlib.import_module("timing_spread_probe")

_WORD = re.compile(r"[A-Za-z']+")
SHOW = "This effect is small at room temperature."


def ssml_both_ends(sentence: str) -> tuple[str, list[str]]:
    """Opening and closing mark per word, split by a break so both survive."""
    words = _WORD.findall(sentence)
    parts = ["<speak>"]
    for i, word in enumerate(words):
        parts.append(
            f'<mark name="w{i}"/>{word}<mark name="e{i}"/>'
            f'<break time="1ms"/> '
        )
    parts.append("</speak>")
    return "".join(parts), words


def half_gap_windows(words, times, total):
    """Each word plus half the quiet on either side. Marks only."""
    start = [times[f"w{i}"] for i in range(len(words))]
    end = [times[f"e{i}"] for i in range(len(words))]
    gap = [
        max(0.0, start[i + 1] - end[i]) if i + 1 < len(words) else None
        for i in range(len(words))
    ]
    out = []
    for i, _w in enumerate(words):
        before = gap[i - 1] / 2 if i and gap[i - 1] is not None else 0.0
        after = gap[i] / 2 if gap[i] is not None else max(0.0, total - end[i])
        out.append((start[i] - before, end[i] + after))
    return out, [g * 1000 for g in gap if g is not None], \
        [(e - s) * 1000 for s, e in zip(start, end)]


def pick(m, heard, rate, spans):
    return [
        [s["sym"] for s in heard
         if lo <= (m.s(s["f0"], rate) + m.s(s["f1"], rate)) / 2 < hi]
        for lo, hi in spans
    ]


def flat25(m, heard, words, times, rate, total):
    out = []
    for i, _w in enumerate(words):
        lo = times[f"w{i}"] - 0.025
        hi = times.get(f"w{i + 1}", total) + 0.025
        out.append([s["sym"] for s in heard
                    if lo <= (m.s(s["f0"], rate) + m.s(s["f1"], rate)) / 2 < hi])
    return out


def units(syms) -> list[str]:
    return split_phone_units(" ".join(syms))


def nm(u: str) -> str:
    return "-".join(unicodedata.name(c, "U%04X" % ord(c)).split()[-1] for c in u)


def main() -> int:
    m = wide.M()
    refs, gaps, durs, dump = {}, [], [], []

    for sent in SWAPS:
        # half-gap, from the break-separated marks
        ssml, words = ssml_both_ends(sent)
        raw, times = synth_voice(ssml, REF_VOICE)
        pcm, rate = pcm_from_wav(raw)
        heard = m.run(pcm, rate)
        spans, g, d = half_gap_windows(words, times, len(pcm) / rate)
        gaps += g
        durs += d
        half = [(w, units(s)) for w, s in zip(words, pick(m, heard, rate, spans))]

        # flat 25ms pad, from the plain marks, as it has been measured all along
        ssml2, words2 = ssml_with_marks(sent)
        raw2, times2 = synth_voice(ssml2, REF_VOICE)
        pcm2, rate2 = pcm_from_wav(raw2)
        heard2 = m.run(pcm2, rate2)
        flat = [(w, units(s)) for w, s in zip(
            words2, flat25(m, heard2, words2, times2, rate2, len(pcm2) / rate2))]

        refs[sent] = {"half": half, "flat": flat}
        if sent == SHOW:
            dump.append(sent)
            for i, word in enumerate(words):
                lo, hi = spans[i]
                dump.append(
                    f"  {word:<12} mark {times[f'w{i}'] * 1000:7.0f} to "
                    f"{times[f'e{i}'] * 1000:7.0f}ms   window "
                    f"{lo * 1000:7.0f} to {hi * 1000:7.0f}ms")
            dump.append("")
            for (w, hu), (_w2, fu) in zip(half, flat):
                dump.append(f"  {w:<12}half {len(hu)}  {' '.join(nm(x) for x in hu)}")
                dump.append(f"  {'':<12}flat {len(fu)}  {' '.join(nm(x) for x in fu)}")
        print(f"ref   {sent[:44]}")

    print(f"\nfrom marks only, {len(durs)} words: length mean "
          f"{stat.mean(durs):.0f}ms median {stat.median(durs):.0f}ms")
    print(f"from marks only, {len(gaps)} gaps: mean {stat.mean(gaps):.0f}ms "
          f"median {stat.median(gaps):.0f}ms min {min(gaps):.0f}ms "
          f"max {max(gaps):.0f}ms")
    print(f"half a gap: median {stat.median(gaps) / 2:.0f}ms  "
          f"({sum(1 for g in gaps if g / 2 < 25)}/{len(gaps)} narrower than 25ms)")

    reads = {}
    for sent, pairs in SWAPS.items():
        for target, wrong in pairs:
            said = re.sub(rf"\b{target}\b", wrong, sent, count=1)
            raw, _t = synth_voice(f"<speak>{said}</speak>", READ_VOICE)
            pcm, rate = pcm_from_wav(raw)
            reads[(sent, target)] = units([s["sym"] for s in m.run(pcm, rate)])

    print(f"\n{'cut':<6}{'judged':>7}{'ref len':>9}  matched on keeping correct "
          f"readings")
    print(f"{'':<6}{'':>7}{'':>9}{'keep 98%':>16}{'keep 95%':>16}{'keep 90%':>16}")
    summary, rows = {}, []
    for cut in ("flat", "half"):
        judged = sum(1 for s in SWAPS for _w, u in refs[s][cut]
                     if len(u) >= _MIN_PHONES)
        lens = [len(u) for s in SWAPS for _w, u in refs[s][cut]]
        tgt, keep = [], []
        for (sent, target), flat_run in reads.items():
            for word, ref_u in refs[sent][cut]:
                if len(ref_u) < _MIN_PHONES:
                    continue
                ratio = best_window_overlap(ref_u, flat_run)
                (tgt if word.lower() == target.lower() else keep).append(ratio)
                rows.append({"cut": cut, "slot": word, "swapped": target,
                             "ref_units": len(ref_u), "ratio": round(ratio, 3),
                             "is_target": word.lower() == target.lower()})
        cells, detail = [], {}
        for want in (0.98, 0.95, 0.90):
            best = None
            for step in range(201):
                line = step / 200
                if sum(1 for r in keep if r >= line) / len(keep) >= want:
                    catch = sum(1 for r in tgt if r < line) / len(tgt)
                    if best is None or catch > best[1]:
                        best = (line, catch)
            cells.append(f"{best[0]:>7.2f}{best[1]:>8.0%}" if best else f"{'-':>15}")
            detail[f"keep{int(want * 100)}"] = {
                "line": best[0], "caught": round(best[1], 3)} if best else None
        print(f"{cut:<6}{judged:>7}{stat.mean(lens):>9.2f}"
              f"{cells[0]}{cells[1]}{cells[2]}")
        summary[cut] = {"judged": judged, "mean_ref_len": round(stat.mean(lens), 2),
                        "targets": len(tgt), "kept": len(keep), **detail}

    pathlib.Path(".cache/halfgap_marks.txt").write_text(
        "\n".join(dump), encoding="utf-8")
    pathlib.Path(".cache/halfgap_marks_report.json").write_text(
        json.dumps({"summary": summary, "rows": rows, "refs": refs,
                    "gaps_ms": gaps, "durations_ms": durs},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nwrote .cache/halfgap_marks_report.json and .cache/halfgap_marks.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
