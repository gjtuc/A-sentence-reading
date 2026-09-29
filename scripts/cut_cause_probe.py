"""design/371 - why does the cut disagree with the mark window?

The bad cuts had to come from one of two sides and neither had been checked
against the audio. A break gives ground truth that needs neither: ask for 600ms
of nothing and then a word, and the word starts when the energy does.

What it found, and it is not what I guessed:

* The mark is not measured off the audio. For six different words it came back
  at 0.596-0.597 every time, which is the break I asked for. It is where the
  word was scheduled, not where it was sung. That is within ~10ms of the audio
  for a word starting on a vowel and much further for one starting on a quiet
  fricative.
* The bigger error is mine. A greedy CTC spike is not where the sound is. The
  model fires once, wherever it is most confident, and that landed between 28ms
  early and 52ms late across the six.
* Forced alignment does not rescue it. Feeding orced_align the sequence the
  model already decoded returns the same frames, because the greedy path is
  already the most likely path for that sequence. The peakiness is in the
  posterior, so re-deriving it from the same posterior cannot move it.

So the two timelines are each wrong by about 30ms, in directions that depend on
the sound, and a sound lasts 20-40ms. The error is larger than the thing being
measured. No arithmetic on marks fixes that.

No IPA reaches the console; cp949 dies on it. Symbols go to the report.

    python scripts/cut_cause_probe.py
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from ctc_reference_probe import MODEL, pcm_from_wav, ssml_with_marks  # noqa: E402
from mark_boundary_probe import TRUTH, synth  # noqa: E402

SENT = "This effect is small at room temperature."
GAP_WORDS = ["film", "small", "is", "at", "people", "each"]


class Aligner:
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
            pathlib.Path(hf_hub_download(MODEL, "vocab.json")).read_text(
                encoding="utf-8"
            )
        )
        cfg = _json.loads(
            pathlib.Path(hf_hub_download(MODEL, "tokenizer_config.json")).read_text(
                encoding="utf-8"
            )
        )
        self.inv = {i: s for s, i in vocab.items()}
        self.pad_id = int(vocab[str(cfg.get("pad_token") or "<pad>")])
        delim = cfg.get("word_delimiter_token")
        self.delim_id = int(vocab[str(delim)]) if delim and str(delim) in vocab else -1
        self.stride = int(self.model.config.inputs_to_logits_ratio)

    def emissions(self, pcm, rate: int):
        values = self.fe(pcm, sampling_rate=rate, return_tensors="pt").input_values
        with self.torch.no_grad():
            logits = self.model(values).logits
        return self.torch.log_softmax(logits, dim=-1)

    def greedy(self, logp) -> list[dict]:
        """What the server produces today: one spike per sound."""
        from itertools import groupby

        ids = logp.argmax(dim=-1)[0].tolist()
        out, frame = [], 0
        for tid, group in groupby(ids):
            n = len(list(group))
            start, frame = frame, frame + n
            if tid == self.pad_id or tid == self.delim_id:
                continue
            out.append({"sym": self.inv[tid], "f0": start, "f1": frame})
        return out

    def aligned(self, logp, token_ids: list[int]) -> list[dict]:
        """Which frames each token owns, by Viterbi over the same emissions."""
        from torchaudio.functional import forced_align, merge_tokens

        targets = self.torch.tensor([token_ids], dtype=self.torch.int32)
        path, scores = forced_align(logp, targets, blank=self.pad_id)
        spans = merge_tokens(path[0], scores[0], blank=self.pad_id)
        return [
            {"sym": self.inv[int(s.token)], "f0": int(s.start), "f1": int(s.end)}
            for s in spans
        ]

    def secs(self, frame: int, rate: int) -> float:
        return frame * self.stride / rate


def onset_seconds(pcm, rate: int, floor=0.02) -> float:
    import numpy as np

    step = rate // 1000
    rms = [
        float(np.sqrt(np.mean(pcm[i * step : (i + 1) * step] ** 2)))
        for i in range(len(pcm) // step)
    ]
    peak = max(rms) or 1.0
    for i, value in enumerate(rms):
        if value > peak * floor:
            return i / 1000.0
    return 0.0


def main() -> int:
    al = Aligner()
    report: dict = {}

    # 1. Against the break ground truth: does a span start closer to the energy
    #    than a spike does?
    gap_rows = []
    for word in GAP_WORDS:
        ssml = f'<speak><break time="600ms"/><mark name="w"/>{word}</speak>'
        raw, times = synth(ssml, 1.0)
        pcm, rate = pcm_from_wav(raw)
        logp = al.emissions(pcm, rate)
        spikes = al.greedy(logp)
        ids = [
            int(i) for i in logp.argmax(dim=-1)[0].tolist()
        ]
        seq: list[int] = []
        for tid in ids:
            if tid in (al.pad_id, al.delim_id):
                continue
            if not seq or seq[-1] != tid:
                seq.append(tid)
        spans = al.aligned(logp, seq)
        truth = onset_seconds(pcm, rate)
        gap_rows.append(
            {
                "word": word,
                "energy_onset_s": round(truth, 3),
                "mark_s": round(times.get("w", -1), 4),
                "spike_s": round(al.secs(spikes[0]["f0"], rate), 3),
                "span_start_s": round(al.secs(spans[0]["f0"], rate), 3),
                "span_end_s": round(al.secs(spans[0]["f1"], rate), 3),
                "spike_err_ms": round(
                    (al.secs(spikes[0]["f0"], rate) - truth) * 1000, 1
                ),
                "span_err_ms": round(
                    (al.secs(spans[0]["f0"], rate) - truth) * 1000, 1
                ),
                "mark_err_ms": round((times.get("w", 0) - truth) * 1000, 1),
            }
        )
        print(
            f"{word:<8} energy={truth:.3f} mark_err="
            f"{gap_rows[-1]['mark_err_ms']:>+6.1f} spike_err="
            f"{gap_rows[-1]['spike_err_ms']:>+6.1f} span_err="
            f"{gap_rows[-1]['span_err_ms']:>+6.1f}"
        )
    report["gap"] = gap_rows
    for key in ("mark_err_ms", "spike_err_ms", "span_err_ms"):
        vals = [abs(r[key]) for r in gap_rows]
        print(f"  mean |{key}| = {sum(vals) / len(vals):.1f}ms  max {max(vals):.1f}ms")

    # 2. The sentence: do the cuts come out right when a span decides, not a spike?
    ssml, words = ssml_with_marks(SENT)
    raw, times = synth(ssml, 1.0)
    pcm, rate = pcm_from_wav(raw)
    logp = al.emissions(pcm, rate)
    spikes = al.greedy(logp)
    seq: list[int] = []
    for tid in logp.argmax(dim=-1)[0].tolist():
        tid = int(tid)
        if tid in (al.pad_id, al.delim_id):
            continue
        if not seq or seq[-1] != tid:
            seq.append(tid)
    spans = al.aligned(logp, seq)

    def cut(items, use_span: bool):
        out = {}
        for i, word in enumerate(words):
            t0 = times[f"w{i}"]
            t1 = times.get(f"w{i + 1}", times["end"])
            picked = []
            for it in items:
                a, b = al.secs(it["f0"], rate), al.secs(it["f1"], rate)
                key = a if use_span else (a + b) / 2
                if t0 <= key < t1:
                    picked.append(it["sym"])
            out[word] = " ".join(picked)
        return out

    by_spike = cut(spikes, use_span=False)
    by_span = cut(spans, use_span=True)
    report["sentence"] = {
        "marks": {k: round(v, 4) for k, v in times.items()},
        "spikes": [
            {"sym": s["sym"], "t": round(al.secs(s["f0"], rate), 3)} for s in spikes
        ],
        "spans": [
            {
                "sym": s["sym"],
                "t0": round(al.secs(s["f0"], rate), 3),
                "t1": round(al.secs(s["f1"], rate), 3),
            }
            for s in spans
        ],
        "by_spike": by_spike,
        "by_span": by_span,
        "truth": TRUTH,
        "wrong_by_spike": [w for w in words if by_spike[w] != TRUTH[w]],
        "wrong_by_span": [w for w in words if by_span[w] != TRUTH[w]],
    }
    print(
        f"\nsentence cuts wrong: spike={len(report['sentence']['wrong_by_spike'])}"
        f"/{len(words)} {','.join(report['sentence']['wrong_by_spike']) or '-'}"
    )
    print(
        f"                     span ={len(report['sentence']['wrong_by_span'])}"
        f"/{len(words)} {','.join(report['sentence']['wrong_by_span']) or '-'}"
    )
    pathlib.Path(".cache/align_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print("wrote .cache/align_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
