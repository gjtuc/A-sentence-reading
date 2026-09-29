"""Synthesise twice: one natural reading to copy, one broken-up one to cut.

The earlier probes kept trying to measure the space between words and kept finding
that asking for it replaces it. That was the wrong worry. Nothing needs the size of
the space. What the reference needs is each word's own sounds, and a break gives
exactly that, because the silence it inserts produces no symbols for a neighbour to
bleed. `small` came out `z s m oo l ae` from the natural reading, carrying the `z`
off `is` and the `ae` off `at`, and `s m oo l` with a break.

Analysis runs once, offline, before anyone practises, so it can synthesise the
sentence twice at no cost to the learner:

  natural - what the learner hears and copies. Unchanged.
  broken  - a break after every word, and a closing mark that now survives, so
            each word's window is exactly [its own start, its own end] plus a pad
            for the model's lag. Only the reference is cut from this.

The cost is that a break long enough to isolate a word may push the voice into
saying words on their own, and this voice says `at` as `a d` alone against `ae t`
in a sentence. A reference built from that would be wrong in a way no amount of
clean cutting fixes. So the break is swept, and every candidate is scored the way
everything else has been: the reference faces a natural reading of the same
sentence with one word swapped for a near miss, and the winner is whichever
catches more wrong words at the same rate of keeping right ones.
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
    best_window_overlap,
    split_phone_units,
)
from ctc_reference_probe import pcm_from_wav, ssml_with_marks  # noqa: E402
from cross_voice_probe import READ_VOICE, REF_VOICE, synth_voice  # noqa: E402
from one_word_wrong_probe import SWAPS  # noqa: E402

import importlib  # noqa: E402

wide = importlib.import_module("timing_spread_probe")

_WORD = re.compile(r"[A-Za-z']+")
BREAKS = [1, 20, 60, 100]
PADS = [0, 25, 50]
SHOW = "This effect is small at room temperature."


def ssml_broken(sentence: str, ms: int) -> tuple[str, list[str]]:
    words = _WORD.findall(sentence)
    parts = ["<speak>"]
    for i, word in enumerate(words):
        parts.append(
            f'<mark name="w{i}"/>{word}<mark name="e{i}"/>'
            f'<break time="{ms}ms"/> '
        )
    parts.append("</speak>")
    return "".join(parts), words


def cut_own(m, heard, words, times, rate, pad_ms, total):
    """Window is the word's own start and end, from marks, plus a pad."""
    pad = pad_ms / 1000.0
    out = []
    for i, word in enumerate(words):
        lo = times[f"w{i}"] - pad
        hi = times.get(f"e{i}", total) + pad
        out.append((word, [
            s["sym"] for s in heard
            if lo <= (m.s(s["f0"], rate) + m.s(s["f1"], rate)) / 2 < hi
        ]))
    return out


def cut_flat(m, heard, words, times, rate, total):
    out = []
    for i, word in enumerate(words):
        lo = times[f"w{i}"] - 0.025
        hi = times.get(f"w{i + 1}", total) + 0.025
        out.append((word, [
            s["sym"] for s in heard
            if lo <= (m.s(s["f0"], rate) + m.s(s["f1"], rate)) / 2 < hi
        ]))
    return out


def units(syms) -> list[str]:
    return split_phone_units(" ".join(syms))


def nm(u: str) -> str:
    return "-".join(unicodedata.name(c, "U%04X" % ord(c)).split()[-1] for c in u)


def collect(refs, reads):
    """One row per (word, take), so builds can be compared on shared words."""
    rows = []
    for (sent, target), run in reads.items():
        for word, ref_u in refs[sent]:
            rows.append({
                "sentence": sent, "slot": word, "swapped": target,
                "ref_units": len(ref_u),
                "judged": len(ref_u) >= _MIN_PHONES,
                "ratio": round(best_window_overlap(ref_u, run), 4)
                if len(ref_u) >= _MIN_PHONES else None,
                "is_target": word.lower() == target.lower(),
            })
    return rows


def rate_at(rows, want):
    """Pass line that keeps want of the correct readings, and what it catches."""
    tgt = [r["ratio"] for r in rows if r["judged"] and r["is_target"]]
    keep = [r["ratio"] for r in rows if r["judged"] and not r["is_target"]]
    if not tgt or not keep:
        return None
    best = None
    for step in range(201):
        line = step / 200
        if sum(1 for r in keep if r >= line) / len(keep) >= want:
            catch = sum(1 for r in tgt if r < line) / len(tgt)
            if best is None or catch > best[1]:
                best = (line, catch, len(tgt), len(keep))
    return best


def score(refs, reads):
    """Caught / kept at the pass line that holds correct readings at each rate."""
    tgt, keep = [], []
    judged = 0
    for (sent, target), run in reads.items():
        for word, ref_u in refs[sent]:
            if len(ref_u) < _MIN_PHONES:
                continue
            ratio = best_window_overlap(ref_u, run)
            (tgt if word.lower() == target.lower() else keep).append(ratio)
    judged = sum(1 for s in refs for _w, u in refs[s] if len(u) >= _MIN_PHONES)
    out = {"judged": judged}
    for want in (0.95, 0.90):
        best = None
        for step in range(201):
            line = step / 200
            if sum(1 for r in keep if r >= line) / len(keep) >= want:
                catch = sum(1 for r in tgt if r < line) / len(tgt)
                if best is None or catch > best[1]:
                    best = (line, catch)
        out[f"keep{int(want * 100)}"] = best
    return out


def main() -> int:
    m = wide.M()

    print("reading the swapped takes naturally, the way a learner would")
    reads = {}
    for sent, pairs in SWAPS.items():
        for target, wrong in pairs:
            said = re.sub(rf"\b{target}\b", wrong, sent, count=1)
            raw, _t = synth_voice(f"<speak>{said}</speak>", READ_VOICE)
            pcm, rate = pcm_from_wav(raw)
            reads[(sent, target)] = units([s["sym"] for s in m.run(pcm, rate)])

    print("baseline: natural reading, 25ms pad both sides")
    natural = {}
    for sent in SWAPS:
        ssml, words = ssml_with_marks(sent)
        raw, times = synth_voice(ssml, REF_VOICE)
        pcm, rate = pcm_from_wav(raw)
        natural[sent] = [
            (w, units(s)) for w, s in cut_flat(
                m, m.run(pcm, rate), words, times, rate, len(pcm) / rate)
        ]

    rowsets = {"natural|25": collect(natural, reads)}
    results = {"natural|25": score(natural, reads)}
    dump = []
    for ms in BREAKS:
        broken = {}
        for sent in SWAPS:
            ssml, words = ssml_broken(sent, ms)
            raw, times = synth_voice(ssml, REF_VOICE)
            pcm, rate = pcm_from_wav(raw)
            heard = m.run(pcm, rate)
            broken[sent] = {
                pad: [(w, units(s)) for w, s in cut_own(
                    m, heard, words, times, rate, pad, len(pcm) / rate)]
                for pad in PADS
            }
            if sent == SHOW:
                dump.append(f"break {ms}ms, pad 25ms")
                for w, u in broken[sent][25]:
                    dump.append(f"  {w:<13}{len(u):>2}  {' '.join(nm(x) for x in u)}")
                dump.append("")
        for pad in PADS:
            key = f"break{ms}|{pad}"
            results[key] = score({s: broken[s][pad] for s in SWAPS}, reads)
            rowsets[key] = collect({s: broken[s][pad] for s in SWAPS}, reads)
        print(f"built break {ms}ms")

    dump.append("natural reading, 25ms pad, for comparison")
    for w, u in natural[SHOW]:
        dump.append(f"  {w:<13}{len(u):>2}  {' '.join(nm(x) for x in u)}")

    print(f"\n{'reference':<16}{'judged':>7}{'keep 95%':>18}{'keep 90%':>18}")
    print(f"{'':<16}{'':>7}{'line':>8}{'caught':>10}{'line':>8}{'caught':>10}")
    for key, r in results.items():
        cells = []
        for want in ("keep95", "keep90"):
            b = r[want]
            cells.append(f"{b[0]:>8.2f}{b[1]:>10.0%}" if b else f"{'-':>18}")
        star = "  <-" if key == "natural|25" else ""
        print(f"{key:<16}{r['judged']:>7}{cells[0]}{cells[1]}{star}")

    # The two builds judge different words, so the headline numbers are not
    # comparable. Compare them again on the words both of them judge.
    base = rowsets["natural|25"]
    shared_report = {}
    print()
    print(f"{'reference':<16}{'shared words':>13}{'keep 95%':>18}{'keep 90%':>18}")
    for key, rows in rowsets.items():
        both = {
            (r["sentence"], r["slot"], r["swapped"])
            for r in rows if r["judged"]
        } & {
            (r["sentence"], r["slot"], r["swapped"])
            for r in base if r["judged"]
        }
        sub = [r for r in rows
               if (r["sentence"], r["slot"], r["swapped"]) in both]
        cells, keep_detail = [], {}
        for want in (0.95, 0.90):
            b = rate_at(sub, want)
            cells.append(f"{b[0]:>8.2f}{b[1]:>10.0%}" if b else f"{'-':>18}")
            keep_detail[f"keep{int(want * 100)}"] = b
        print(f"{key:<16}{len(both):>13}{cells[0]}{cells[1]}")
        shared_report[key] = {"shared": len(both), **keep_detail}

    # Which words does the contaminated cut judge that the clean cut will not?
    clean = {(r["sentence"], r["slot"]) for r in rowsets["break100|25"]
             if r["judged"]}
    only_dirty = sorted({
        (r["slot"], r["ref_units"]) for r in base
        if r["judged"] and (r["sentence"], r["slot"]) not in clean
    })
    print(f"\njudged only because a neighbour's sounds came along: "
          f"{len(only_dirty)} words")
    print("   " + ", ".join(f"{w}({n})" for w, n in only_dirty))

    pathlib.Path(".cache/two_voices.txt").write_text(
        "\n".join(dump), encoding="utf-8")
    pathlib.Path(".cache/two_voices_report.json").write_text(
        json.dumps({"results": results, "shared": shared_report,
                    "rowsets": rowsets},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nwrote .cache/two_voices_report.json and .cache/two_voices.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
