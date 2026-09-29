"""Does a per-symbol lag table beat the blanket pad?

The lag is ordered by symbol: the wide sample put a word-initial vowel at +14ms
and a word-initial `l` at +79ms. That is physics, not noise, so the obvious next
move is a table — look up each sound's own lag and move it back by exactly that,
instead of widening every window by the same amount.

The table has two problems a pad does not. Inside one symbol the lag still swings
(`z` ran from -9 to +85 on five samples), and a table only knows the symbols it
has seen. So the table is tested here the same way the pad was: build the
reference from one voice, score a different voice reading the same sentence
(should pass) and reading a different sentence (should not).

Judged on the only figures that matter: how many words are long enough to judge,
how many correct readings pass, how many wrong readings pass.
"""
from __future__ import annotations

import json
import pathlib
import statistics as stat
import sys

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

import importlib  # noqa: E402

wide = importlib.import_module("timing_spread_probe")

SENTENCES = [
    "The film grew at five hundred degrees.",
    "The catalyst was prepared by chemical vapour deposition.",
    "We measured the dispersion of the nanoparticles in water.",
    "This effect is small at room temperature.",
    "The single cell performance was stable for one hundred hours.",
    "A thin layer forms on the surface of the gold.",
    "Energy is released when the oxide is reduced.",
    "The light passes through the water without loss.",
    "Both peaks shift towards lower energy under pressure.",
    "Zinc oxide shows strong absorption in the ultraviolet.",
]

# ("how the window is placed", pad in ms)
MODES = [
    ("pad", 0),
    ("pad", 25),
    ("table", 0),
    ("table", 10),
    ("table", 25),
]


def load_table(min_n: int = 2) -> tuple[dict[str, float], float]:
    """Per-symbol lag in seconds, plus the fallback for unseen symbols."""
    report = json.loads(
        pathlib.Path(".cache/pertoken_report.json").read_text(encoding="utf-8")
    )
    table = {
        sym: v["mean"] / 1000.0
        for sym, v in report["table"].items()
        if v["n"] >= min_n
    }
    return table, report["all"]["mean"] / 1000.0


def place(m, heard, words, times, rate, how: str, pad_ms: float, table, fallback):
    """One (word, sounds) pair per word, under one window-placing rule."""
    pad = pad_ms / 1000.0
    marks = []
    for s in heard:
        t0, t1 = m.s(s["f0"], rate), m.s(s["f1"], rate)
        if how == "table":
            lag = table.get(s["sym"], fallback)
            t0, t1 = t0 - lag, t1 - lag
        marks.append(((t0 + t1) / 2, s["sym"]))
    out = []
    for i, word in enumerate(words):
        lo = times[f"w{i}"] - pad
        hi = times.get(f"w{i + 1}", times["end"]) + pad
        out.append((word, " ".join(sym for mid, sym in marks if lo <= mid < hi)))
    return out


def main() -> int:
    m = wide.M()
    table, fallback = load_table()
    print(f"table holds {len(table)} symbols, fallback {fallback * 1000:+.1f}ms")

    refs, reads = [], []
    for sent in SENTENCES:
        ssml, words = ssml_with_marks(sent)
        raw, times = synth_voice(ssml, REF_VOICE)
        pcm, rate = pcm_from_wav(raw)
        heard = m.run(pcm, rate)
        cuts = {
            f"{how}{pad}": place(
                m, heard, words, times, rate, how, pad, table, fallback
            )
            for how, pad in MODES
        }
        refs.append({"sentence": sent, "cuts": cuts})

        r_raw, _t = synth_voice(f"<speak>{sent}</speak>", READ_VOICE)
        r_pcm, r_rate = pcm_from_wav(r_raw)
        reads.append(" ".join(s["sym"] for s in m.run(r_pcm, r_rate)))
        print(f"built {sent[:40]:<40} ref_syms={len(heard)}")

    print(f"\nreference {REF_VOICE}, reading {READ_VOICE}")
    print(f"threshold {_OVERLAP_MIN}, floor {_MIN_PHONES} sounds, "
          f"{sum(len(r['cuts'][f'pad0']) for r in refs)} words per mode")
    print(f"\n{'mode':<10}{'judged':>8}{'correct pass':>14}{'wrong pass':>12}"
          f"{'ref len':>9}")
    summary, rows = {}, []
    for how, pad in MODES:
        key = f"{how}{pad}"
        judged = 0
        good = {"n": 0, "pass": 0, "sum": 0.0}
        bad = {"n": 0, "pass": 0, "sum": 0.0}
        lens = []
        for ri, ref in enumerate(refs):
            for word, phone in ref["cuts"][key]:
                lens.append(len(split_phone_units(phone)))
            for role, other in (("same", ri), ("other", (ri + 1) % len(refs))):
                flat = split_phone_units(reads[other])
                for word, phone in ref["cuts"][key]:
                    units = split_phone_units(phone)
                    if len(units) < _MIN_PHONES:
                        continue
                    ratio = best_window_overlap(units, flat)
                    b = good if role == "same" else bad
                    b["n"] += 1
                    b["sum"] += ratio
                    if ratio >= _OVERLAP_MIN:
                        b["pass"] += 1
                    rows.append({
                        "mode": key, "role": role, "word": word,
                        "units": len(units), "ratio": round(ratio, 3),
                    })
        judged = good["n"]
        g = good["pass"] / good["n"] if good["n"] else 0.0
        b = bad["pass"] / bad["n"] if bad["n"] else 0.0
        print(f"{key:<10}{judged:>8}{good['pass']:>6}/{good['n']:<3}{g:>7.1%}"
              f"{bad['pass']:>5}/{bad['n']:<3}{b:>6.1%}{stat.mean(lens):>9.2f}")
        summary[key] = {
            "judged": judged,
            "correct_pass": round(g, 3),
            "wrong_pass": round(b, 3),
            "mean_ratio_correct": round(good["sum"] / good["n"], 3) if good["n"] else 0,
            "mean_ratio_wrong": round(bad["sum"] / bad["n"], 3) if bad["n"] else 0,
            "mean_ref_len": round(stat.mean(lens), 2),
        }

    pathlib.Path(".cache/table_vs_pad_report.json").write_text(
        json.dumps({"summary": summary, "rows": rows, "refs": refs, "reads": reads},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print("\nwrote .cache/table_vs_pad_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
