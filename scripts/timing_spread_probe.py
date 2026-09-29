"""design/371 - how big is the timing error, a word, and the gap between words?

48 words and 10 sentences, because the six-word sample was too small to tell a
bias from scatter and the ground truth in it was wrong.

The fix to the ground truth is the reason the numbers moved. A word is asked for
after 600ms of silence, and the onset is the first sample that leaves the noise
floor **of that silence**. The earlier probe gated on a fraction of the loudest
sample instead, which misses a quiet  and the closure before a p, and those
were exactly the two rows that made the mark look bad.

What it found:

* The mark is good. Mean +7.1ms, sd 5.7, worst +18.4. It is not the problem, and
  the 27ms reported before was the bad gate, not Google.
* The spike is late, and consistently: mean +50.2ms, sd 24.7, every sound class
  between +37 (vowel) and +69 (nasal). After silence, anyway.
* The posterior is no wider than the spike where it counts. Taking the frame
  where the probability starts to rise moves the onset 0.4ms. Not a way out.
* A word runs 302ms at the median and 55ms at the shortest.
* The gap between words is 60ms at the median, but 4 of 75 boundaries have no
  gap at all and only 15 of 75 go properly quiet.

The lateness looks subtractable and is not: inside connected speech the lag runs
20-60ms, not a steady 50, so a constant correction moved the truth sentence from
3 wrong to 5 and count agreement from 74% to 30%. The spread is the problem, not
the mean.
"""
from __future__ import annotations

import json
import pathlib
import statistics as stat
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from ctc_reference_probe import MODEL, pcm_from_wav, ssml_with_marks  # noqa: E402
from mark_boundary_probe import synth  # noqa: E402

GAP_MS = 600

WORDS = {
    "vowel": ["at", "is", "each", "on", "up", "in", "all", "every", "oxide", "energy"],
    "plosive": ["people", "but", "take", "do", "can", "get", "put", "dark", "gold",
                "boundary"],
    "fricative": ["film", "small", "see", "five", "for", "this", "have", "show",
                  "thin", "surface"],
    "nasal": ["no", "my", "more", "new", "near", "name", "measured", "nanometers"],
    "liquid": ["room", "light", "we", "will", "one", "year", "red", "low", "water",
               "layer"],
}

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
]


class M:
    def __init__(self) -> None:
        import json as _json

        import torch
        from huggingface_hub import hf_hub_download
        from transformers import Wav2Vec2FeatureExtractor, Wav2Vec2ForCTC

        self.torch = torch
        self.fe = Wav2Vec2FeatureExtractor.from_pretrained(MODEL)
        self.model = Wav2Vec2ForCTC.from_pretrained(MODEL)
        self.model.eval()
        vocab = _json.loads(
            pathlib.Path(hf_hub_download(MODEL, "vocab.json")).read_text("utf-8")
        )
        cfg = _json.loads(
            pathlib.Path(hf_hub_download(MODEL, "tokenizer_config.json")).read_text(
                "utf-8"
            )
        )
        self.inv = {i: s for s, i in vocab.items()}
        self.pad = int(vocab[str(cfg.get("pad_token") or "<pad>")])
        d = cfg.get("word_delimiter_token")
        self.delim = int(vocab[str(d)]) if d and str(d) in vocab else -1
        self.stride = 320

    def run(self, pcm, rate):
        """Symbols with the argmax frame run and the frames the posterior covers."""
        from itertools import groupby

        values = self.fe(pcm, sampling_rate=rate, return_tensors="pt").input_values
        with self.torch.no_grad():
            logits = self.model(values).logits
        prob = self.torch.softmax(logits, dim=-1)[0]
        ids = logits.argmax(dim=-1)[0].tolist()
        out, frame = [], 0
        for tid, group in groupby(ids):
            n = len(list(group))
            f0, frame = frame, frame + n
            if tid in (self.pad, self.delim):
                continue
            # Where the probability for this sound rises and falls around the
            # spike, at a tenth of its peak there.
            col = prob[:, tid]
            peak = float(col[f0:frame].max())
            lo = f0
            while lo > 0 and float(col[lo - 1]) > peak * 0.1:
                lo -= 1
            hi = frame
            while hi < col.shape[0] and float(col[hi]) > peak * 0.1:
                hi += 1
            out.append(
                {"sym": self.inv[tid], "f0": f0, "f1": frame, "p0": lo, "p1": hi}
            )
        return out

    def s(self, frame, rate):
        return frame * self.stride / rate


def onset_from_silence(pcm, rate, quiet_s=0.40):
    """First sample that leaves the noise floor of the leading silence."""
    import numpy as np

    step = max(1, rate // 1000)
    quiet = np.abs(pcm[: int(quiet_s * rate)])
    floor = float(quiet.max()) if quiet.size else 0.0
    gate = max(floor * 3.0, 3e-4)
    mag = np.abs(pcm)
    frames = len(mag) // step
    for i in range(frames):
        if float(mag[i * step : (i + 1) * step].max()) > gate:
            return i / 1000.0
    return 0.0


def rms_series(pcm, rate, win_ms=10):
    import numpy as np

    step = max(1, int(rate * win_ms / 1000))
    return np.array(
        [
            float(np.sqrt(np.mean(pcm[i * step : (i + 1) * step] ** 2)))
            for i in range(len(pcm) // step)
        ]
    ), win_ms / 1000.0


def main() -> int:
    m = M()
    report: dict = {"frame_ms": 20.0, "receptive_field_ms": 25.0}

    # A. the error, over a wide sample
    word_rows = []
    for klass, words in WORDS.items():
        for word in words:
            ssml = f'<speak><break time="{GAP_MS}ms"/><mark name="w"/>{word}</speak>'
            raw, times = synth(ssml, 1.0)
            pcm, rate = pcm_from_wav(raw)
            heard = m.run(pcm, rate)
            if not heard:
                continue
            truth = onset_from_silence(pcm, rate)
            first = heard[0]
            word_rows.append(
                {
                    "word": word,
                    "class": klass,
                    "truth_s": round(truth, 4),
                    "mark_err_ms": round((times.get("w", 0) - truth) * 1000, 1),
                    "spike_err_ms": round((m.s(first["f0"], rate) - truth) * 1000, 1),
                    "post_err_ms": round((m.s(first["p0"], rate) - truth) * 1000, 1),
                    "n_sym": len(heard),
                    "sound_s": round(
                        m.s(heard[-1]["f1"], rate) - m.s(first["f0"], rate), 4
                    ),
                }
            )
    report["words"] = word_rows
    print(f"words measured: {len(word_rows)}")

    def spread(key):
        v = [r[key] for r in word_rows]
        a = [abs(x) for x in v]
        return {
            "mean": round(stat.mean(v), 1),
            "sd": round(stat.pstdev(v), 1),
            "min": min(v),
            "max": max(v),
            "mean_abs": round(stat.mean(a), 1),
            "p90_abs": round(sorted(a)[int(len(a) * 0.9)], 1),
            "range": round(max(v) - min(v), 1),
        }

    report["error_spread"] = {k: spread(k) for k in
                             ("mark_err_ms", "spike_err_ms", "post_err_ms")}
    print("\nerror spread (ms), onset vs ground truth")
    print(f"{'source':<14}{'mean':>7}{'sd':>7}{'min':>7}{'max':>7}{'|mean|':>8}{'p90':>7}{'range':>7}")
    for key, v in report["error_spread"].items():
        print(f"{key:<14}{v['mean']:>7}{v['sd']:>7}{v['min']:>7}{v['max']:>7}"
              f"{v['mean_abs']:>8}{v['p90_abs']:>7}{v['range']:>7}")

    print("\nby first sound")
    by = {}
    for klass in WORDS:
        rows = [r for r in word_rows if r["class"] == klass]
        if not rows:
            continue
        by[klass] = {
            "n": len(rows),
            "mark_mean": round(stat.mean(r["mark_err_ms"] for r in rows), 1),
            "spike_mean": round(stat.mean(r["spike_err_ms"] for r in rows), 1),
            "spike_mean_abs": round(stat.mean(abs(r["spike_err_ms"]) for r in rows), 1),
        }
        print(f"  {klass:<10} n={by[klass]['n']:<3} mark={by[klass]['mark_mean']:>+7.1f} "
              f"spike={by[klass]['spike_mean']:>+7.1f} |spike|={by[klass]['spike_mean_abs']:>6.1f}")
    report["by_class"] = by

    # B. word length and the gap between words, inside real sentences
    gaps, durs, dips, sent_rows = [], [], [], []
    for sent in SENTENCES:
        ssml, words = ssml_with_marks(sent)
        raw, times = synth(ssml, 1.0)
        pcm, rate = pcm_from_wav(raw)
        heard = m.run(pcm, rate)
        rms, win = rms_series(pcm, rate)
        loud = float(rms.mean()) or 1.0
        per = []
        for i, word in enumerate(words):
            t0 = times[f"w{i}"]
            t1 = times.get(f"w{i + 1}", times["end"])
            inside = [s for s in heard if t0 <= (m.s(s["f0"], rate) + m.s(s["f1"], rate)) / 2 < t1]
            dur = (t1 - t0) * 1000
            durs.append(dur)
            per.append({"word": word, "mark_dur_ms": round(dur, 1), "n_sym": len(inside)})
            if i + 1 < len(words):
                # Silence at the boundary: the quietest 10ms within +-60ms of it.
                lo = max(0, int((t1 - 0.06) / win))
                hi = min(len(rms), int((t1 + 0.06) / win) + 1)
                dip = float(rms[lo:hi].min()) / loud if hi > lo else 1.0
                dips.append(dip)
            if i + 1 < len(words) and inside:
                nxt_t0 = times[f"w{i + 1}"]
                nxt_t1 = times.get(f"w{i + 2}", times["end"])
                nxt = [s for s in heard
                       if nxt_t0 <= (m.s(s["f0"], rate) + m.s(s["f1"], rate)) / 2 < nxt_t1]
                if nxt:
                    gap = (m.s(nxt[0]["f0"], rate) - m.s(inside[-1]["f1"], rate)) * 1000
                    gaps.append(gap)
        sent_rows.append({"sentence": sent, "words": per})
    report["sentences"] = sent_rows
    report["word_duration_ms"] = {
        "n": len(durs), "mean": round(stat.mean(durs), 1),
        "median": round(stat.median(durs), 1), "min": round(min(durs), 1),
        "p10": round(sorted(durs)[int(len(durs) * 0.1)], 1),
    }
    report["ctc_gap_ms"] = {
        "n": len(gaps), "mean": round(stat.mean(gaps), 1),
        "median": round(stat.median(gaps), 1), "min": round(min(gaps), 1),
        "max": round(max(gaps), 1),
        "under_20": sum(1 for g in gaps if g < 20),
        "under_40": sum(1 for g in gaps if g < 40),
        "zero_or_less": sum(1 for g in gaps if g <= 0),
    }
    report["boundary_quiet_ratio"] = {
        "n": len(dips), "mean": round(stat.mean(dips), 3),
        "median": round(stat.median(dips), 3), "min": round(min(dips), 3),
        "max": round(max(dips), 3),
        "really_silent_under_5pct": sum(1 for d in dips if d < 0.05),
    }
    print("\nword duration from marks (ms): " + json.dumps(report["word_duration_ms"]))
    print("gap between words in symbol time (ms): " + json.dumps(report["ctc_gap_ms"]))
    print("how quiet the boundary gets, vs sentence mean: "
          + json.dumps(report["boundary_quiet_ratio"]))

    pathlib.Path(".cache/wide_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print("\nwrote .cache/wide_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
