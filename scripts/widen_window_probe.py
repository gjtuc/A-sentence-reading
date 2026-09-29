"""design/371 - widen the mark window instead of moving it.

The earlier probe moved the whole grid of marks, which was the wrong experiment.
Moving cannot help: is is marked across 85ms while its sounds occupy 120ms, so
no offset makes a short window hold them. A window has to get wider.

Widening lets two words claim the same sound, so one number will not do:

* whole - every one of the word's own sounds is inside its window
* extra - how many sounds belonging to a neighbour came along

At 25ms, which is the spread measured in 	iming_spread_probe.py, all seven
words of the hand-read sentence come out whole, against five at zero. Across 44
more words the count that is short of the word's own drops from 11 to 4. The cost
is about one extra sound per word, and cross_voice_probe.py is what shows that
cost is not paid at scoring time.
"""
from __future__ import annotations

import json
import pathlib
import statistics as stat
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from ctc_reference_probe import pcm_from_wav, ssml_with_marks  # noqa: E402
from mark_boundary_probe import TRUTH, synth  # noqa: E402

import importlib  # noqa: E402

wide = importlib.import_module("timing_spread_probe")

TRUTH_SENT = "This effect is small at room temperature."
MORE = [
    "The film grew at five hundred degrees.",
    "We measured the dispersion of the nanoparticles in water.",
    "The single cell performance was stable for one hundred hours.",
    "A thin layer forms on the surface of the gold.",
    "The boundary between the two phases is sharp.",
]
STEPS = [0, 10, 20, 25, 30, 40, 50, 60, 80]


def widen_cut(m, heard, words, times, rate, pad_ms: float):
    """Window per word, grown by `pad_ms` at both ends. Overlap is allowed."""
    pad = pad_ms / 1000.0
    out = []
    for i, word in enumerate(words):
        t0 = times[f"w{i}"] - pad
        t1 = times.get(f"w{i + 1}", times["end"]) + pad
        picked = [
            s["sym"]
            for s in heard
            if t0 <= (m.s(s["f0"], rate) + m.s(s["f1"], rate)) / 2 < t1
        ]
        out.append((word, picked))
    return out


def contains_in_order(got: list[str], want: list[str]) -> bool:
    """Every wanted sound present, in order, extras allowed between."""
    it = iter(got)
    return all(any(g == w for g in it) for w in want)


def main() -> int:
    m = wide.M()
    report: dict = {}

    # 1. hand truth: recall and extras, as the window grows
    ssml, words = ssml_with_marks(TRUTH_SENT)
    raw, times = synth(ssml, 1.0)
    pcm, rate = pcm_from_wav(raw)
    heard = m.run(pcm, rate)
    print("hand truth sentence, window grown at both ends")
    print(f"{'pad_ms':>7}{'whole':>8}{'exact':>8}{'extra/word':>12}  missing")
    hand = []
    for pad in STEPS:
        got = widen_cut(m, heard, words, times, rate, pad)
        whole, exact, extras, missing = 0, 0, 0, []
        for word, syms in got:
            want = TRUTH[word].split()
            if contains_in_order(syms, want):
                whole += 1
                extras += len(syms) - len(want)
                if len(syms) == len(want):
                    exact += 1
            else:
                missing.append(word)
        hand.append(
            {
                "pad_ms": pad, "whole": whole, "exact": exact,
                "extra_total": extras, "missing": missing,
                "cuts": {w: " ".join(s) for w, s in got},
            }
        )
        print(f"{pad:>7}{whole:>6}/{len(words)}{exact:>6}/{len(words)}"
              f"{extras / len(words):>12.2f}  {','.join(missing) or '-'}")
    report["hand"] = hand

    # 2. more sentences: how does the sound count move against the count the
    #    word has on its own?
    print("\nfive more sentences, count against the word asked for alone")
    alone: dict[str, int] = {}
    sent_data = []
    for sent in MORE:
        s_ssml, s_words = ssml_with_marks(sent)
        s_raw, s_times = synth(s_ssml, 1.0)
        s_pcm, s_rate = pcm_from_wav(s_raw)
        s_heard = m.run(s_pcm, s_rate)
        for word in s_words:
            if word not in alone:
                a_raw, _t = synth(f'<speak><break time="400ms"/>{word}</speak>', 1.0)
                a_pcm, a_rate = pcm_from_wav(a_raw)
                alone[word] = len(m.run(a_pcm, a_rate))
        sent_data.append((s_words, s_heard, s_times, s_rate))

    print(f"{'pad_ms':>7}{'short':>8}{'equal':>8}{'over':>7}{'mean_diff':>11}")
    scale = []
    for pad in STEPS:
        diffs = []
        for s_words, s_heard, s_times, s_rate in sent_data:
            for word, syms in widen_cut(m, s_heard, s_words, s_times, s_rate, pad):
                diffs.append(len(syms) - alone[word])
        row = {
            "pad_ms": pad, "n": len(diffs),
            "short": sum(1 for d in diffs if d < 0),
            "equal": sum(1 for d in diffs if d == 0),
            "over": sum(1 for d in diffs if d > 0),
            "mean_diff": round(stat.mean(diffs), 2),
        }
        scale.append(row)
        print(f"{pad:>7}{row['short']:>6}/{row['n']}{row['equal']:>6}/{row['n']}"
              f"{row['over']:>7}{row['mean_diff']:>11}")
    report["scale"] = scale
    report["alone"] = alone

    pathlib.Path(".cache/widen_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print("\nwrote .cache/widen_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
