"""Is the lag a property of the sound symbol, and tight enough to subtract?

The class means already say the lag is structured: +37ms for a vowel, +69ms for
a nasal. If it is structured per symbol and not just per class, a table beats a
blanket pad, because a pad widens every window while a table moves each sound to
where it actually happened.

Ground truth is the mark, which the wide sample put at 7ms. For every word in
every sentence, the first sound's spike minus that word's mark is one sample of
that symbol's lag, measured inside connected speech, where the 50ms figure from
the silence test does not hold.

The number that decides it is the residual: if subtracting each symbol's own mean
collapses the spread, the lag belongs to the symbol. If it does not, the spread is
something else and a table cannot help.
"""
from __future__ import annotations

import json
import pathlib
import statistics as stat
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from ctc_reference_probe import pcm_from_wav, ssml_with_marks  # noqa: E402
from mark_boundary_probe import synth  # noqa: E402

import importlib  # noqa: E402

wide = importlib.import_module("timing_spread_probe")

SENTENCES = [
    "The film grew at five hundred degrees.",
    "The catalyst was prepared by chemical vapour deposition.",
    "We measured the dispersion of the nanoparticles in water.",
    "This effect is small at room temperature.",
    "The single cell performance was stable for one hundred hours.",
    "A thin layer forms on the surface of the gold.",
    "The boundary between the two phases is sharp.",
    "Energy is released when the oxide is reduced.",
    "Each sample was heated for one hour and then cooled.",
    "The light passes through the water without loss.",
    "Most of the current flows along the edge.",
    "Nearly all of the signal comes from the top layer.",
    "Such behaviour has been reported for similar systems.",
    "Both peaks shift towards lower energy under pressure.",
    "Very little change occurs below the critical point.",
    "Good agreement between theory and measurement was found.",
    "Junction resistance drops sharply above the threshold.",
    "Zinc oxide shows strong absorption in the ultraviolet.",
    "Values given here refer to the mean of ten runs.",
    "Yellow crystals formed slowly over several days.",
    "Chemical shifts confirm the presence of the ligand.",
    "Thermal treatment removes the remaining solvent.",
    "Under vacuum the sample loses mass steadily.",
    "Only the outer shell takes part in the reaction.",
    "Inner regions remain unchanged after long exposure.",
    "Pressure was held constant during every cycle.",
    "Field emission occurs at relatively low voltage.",
    "Long chains pack tightly within the crystal.",
    "Rough surfaces scatter far more of the beam.",
    "Weak coupling explains the narrow line width.",
    "Doping raises the carrier density by two orders.",
    "Because the barrier is thin, tunnelling dominates.",
    "Above five kelvin the resistance rises again.",
    "Oxygen vacancies control the colour of the film.",
    "Iron rich phases appear near the interface.",
    "Sharp features indicate a well ordered lattice.",
]


def main() -> int:
    m = wide.M()
    samples: list[dict] = []
    sents = []
    for sent in SENTENCES:
        ssml, words = ssml_with_marks(sent)
        raw, times = synth(ssml, 1.0)
        pcm, rate = pcm_from_wav(raw)
        heard = m.run(pcm, rate)
        sents.append((sent, words, times, heard, rate))
        for i, word in enumerate(words):
            t0 = times[f"w{i}"]
            t1 = times.get(f"w{i + 1}", times["end"])
            inside = [
                s for s in heard
                if t0 <= (m.s(s["f0"], rate) + m.s(s["f1"], rate)) / 2 < t1
            ]
            if not inside:
                continue
            first = inside[0]
            samples.append(
                {
                    "word": word,
                    "sym": first["sym"],
                    "lag_ms": round((m.s(first["f0"], rate) - t0) * 1000, 1),
                }
            )
    print(f"sentences {len(SENTENCES)}  word-initial samples {len(samples)}")

    all_lags = [s["lag_ms"] for s in samples]
    by_sym: dict[str, list[float]] = {}
    for s in samples:
        by_sym.setdefault(s["sym"], []).append(s["lag_ms"])

    # The test: does each symbol's own mean explain the spread?
    resid = [
        s["lag_ms"] - stat.mean(by_sym[s["sym"]])
        for s in samples
        if len(by_sym[s["sym"]]) >= 2
    ]
    print(f"\nall word-initial lags:  mean {stat.mean(all_lags):+.1f}ms  "
          f"sd {stat.pstdev(all_lags):.1f}  min {min(all_lags):+.1f}  "
          f"max {max(all_lags):+.1f}")
    print(f"after subtracting each symbol's own mean: sd {stat.pstdev(resid):.1f}ms  "
          f"(n={len(resid)})")
    drop = 1 - (stat.pstdev(resid) / stat.pstdev(all_lags))
    print(f"spread removed by a per-symbol table: {drop:.1%}")

    table = {}
    for sym, lags in sorted(by_sym.items(), key=lambda kv: -len(kv[1])):
        if len(lags) < 2:
            continue
        table[sym] = {
            "n": len(lags), "mean": round(stat.mean(lags), 1),
            "sd": round(stat.pstdev(lags), 1),
            "min": min(lags), "max": max(lags),
        }
    singles = sum(1 for lags in by_sym.values() if len(lags) < 2)
    sd_of_means = stat.pstdev([v["mean"] for v in table.values()])
    within = stat.mean([v["sd"] for v in table.values()])
    print(f"distinct symbols {len(by_sym)}, of which seen once {singles}")
    print(f"spread between symbols (sd of means) {sd_of_means:.1f}ms")
    print(f"spread inside one symbol (mean sd)   {within:.1f}ms")
    # The pad has to cover whatever the table cannot explain.
    print(f"pad the spread asks for now:        {stat.pstdev(all_lags):.1f}ms")
    print(f"pad the spread asks for with table: {stat.pstdev(resid):.1f}ms")

    pathlib.Path(".cache/pertoken_report.json").write_text(
        json.dumps(
            {
                "n_samples": len(samples),
                "all": {"mean": round(stat.mean(all_lags), 1),
                        "sd": round(stat.pstdev(all_lags), 1)},
                "residual_sd": round(stat.pstdev(resid), 1),
                "spread_removed": round(drop, 3),
                "sd_between_symbols": round(sd_of_means, 1),
                "mean_sd_within_symbol": round(within, 1),
                "table": table,
                "samples": samples,
            },
            ensure_ascii=False, indent=1,
        ),
        encoding="utf-8",
    )
    print("\nwrote .cache/pertoken_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
