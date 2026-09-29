"""design/371 - cut the native voice into per-word reference sounds, and ask
whether word order makes short words reachable.

Two jobs, because the second needs the first:

1. Ask Google TTS for the sentence with an SSML mark before every word and get
   the mark times back, so the audio has known word boundaries. Run the same
   waveform model the server runs on takes, keep the frame each symbol landed
   on, and cut the run at the word boundaries. That is a reference sound per
   printed word, made from a voice and measured by the model that will measure
   the reader.

2. design/366 refuses to judge a word whose reference is under three sounds,
   because searching a whole sentence for a two-sound target finds a match by
   accident. Measure that: compare every word against the run from its own
   sentence (a perfect read) and against the run from a different sentence (a
   word the reader never said). Then repeat both with the search restricted to
   the region word order allows, and see whether the accidental matches go away.

No IPA reaches the console; cp949 dies on it. Symbols go to the JSON only.

    python scripts/ctc_reference_probe.py --out data/ctc_ref_probe.json
"""

from __future__ import annotations

import argparse
import io
import json
import pathlib
import re
import sys
import wave

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from sentence_reading.llm.phone_match import (  # noqa: E402
    _MIN_PHONES,
    _OVERLAP_MIN,
    overlap_ratio,
    split_phone_units,
)

MODEL = "facebook/wav2vec2-lv-60-espeak-cv-ft"

# Real paper sentences, picked so the set has short function words to test.
SENTENCES = [
    "The film grew at five hundred degrees.",
    "The catalyst was prepared by chemical vapour deposition.",
    "We measured the dispersion of the nanoparticles in water.",
    "This effect is small at room temperature.",
    "The single cell performance was stable for one hundred hours.",
]

_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")


def ssml_with_marks(sentence: str) -> tuple[str, list[str]]:
    """SSML with a mark before each word and one after the last.

    The mark names are what come back with times, so word `i` is the audio
    between mark `i` and mark `i + 1`.
    """
    words = _WORD.findall(sentence)
    parts = ["<speak>"]
    for i, word in enumerate(words):
        parts.append(f'<mark name="w{i}"/>{word} ')
    parts.append('<mark name="end"/></speak>')
    return "".join(parts), words


def synthesize_with_timepoints(sentence: str, voice: str) -> tuple[bytes, dict]:
    """LINEAR16 16 kHz bytes plus {mark_name: seconds}.

    LINEAR16 on purpose: the wav decodes with the standard library, so this needs
    no ffmpeg. Timepoints are v1beta1 only.
    """
    from google.cloud import texttospeech_v1beta1 as tts

    ssml, _words = ssml_with_marks(sentence)
    client = tts.TextToSpeechClient()
    request = tts.SynthesizeSpeechRequest(
        input=tts.SynthesisInput(ssml=ssml),
        voice=tts.VoiceSelectionParams(
            language_code="-".join(voice.split("-")[:2]), name=voice
        ),
        audio_config=tts.AudioConfig(
            audio_encoding=tts.AudioEncoding.LINEAR16, sample_rate_hertz=16000
        ),
        enable_time_pointing=[tts.SynthesizeSpeechRequest.TimepointType.SSML_MARK],
    )
    answer = client.synthesize_speech(request=request)
    times = {p.mark_name: float(p.time_seconds) for p in answer.timepoints}
    return answer.audio_content, times


def pcm_from_wav(raw: bytes):
    """Mono float32 at 16 kHz from LINEAR16 wav bytes."""
    import numpy as np

    with wave.open(io.BytesIO(raw), "rb") as fh:
        assert fh.getsampwidth() == 2, fh.getsampwidth()
        assert fh.getnchannels() == 1, fh.getnchannels()
        rate = fh.getframerate()
        frames = fh.readframes(fh.getnframes())
    pcm = np.frombuffer(frames, dtype="<i2").astype("float32") / 32768.0
    return pcm, rate


class Hearer:
    """The server's waveform pass, kept at frame resolution.

    The server calls `Wav2Vec2Processor`, whose tokenizer will not even build
    without eSpeak on the box, and whose `batch_decode` throws the frame each
    symbol landed on away. Both are avoided by reading `vocab.json` and doing the
    CTC collapse here. The collapse is the library's, symbol for symbol: group
    runs of the same id, drop the blank, drop the word delimiter, join on spaces.
    """

    def __init__(self) -> None:
        import torch
        from huggingface_hub import hf_hub_download
        from transformers import Wav2Vec2FeatureExtractor, Wav2Vec2ForCTC

        self.torch = torch
        self.fe = Wav2Vec2FeatureExtractor.from_pretrained(MODEL)
        self.model = Wav2Vec2ForCTC.from_pretrained(MODEL)
        self.model.eval()
        vocab = json.loads(
            pathlib.Path(hf_hub_download(MODEL, "vocab.json")).read_text(
                encoding="utf-8"
            )
        )
        cfg = json.loads(
            pathlib.Path(hf_hub_download(MODEL, "tokenizer_config.json")).read_text(
                encoding="utf-8"
            )
        )
        self.inv = {i: s for s, i in vocab.items()}
        self.pad = str(cfg.get("pad_token") or "<pad>")
        delim = cfg.get("word_delimiter_token")
        self.delim = str(delim) if delim else None
        self.stride = int(self.model.config.inputs_to_logits_ratio)

    def hear(self, pcm, rate: int) -> list[dict]:
        """One entry per surviving symbol: its text and the seconds it covers."""
        from itertools import groupby

        values = self.fe(pcm, sampling_rate=rate, return_tensors="pt").input_values
        with self.torch.no_grad():
            logits = self.model(values).logits
        ids = self.torch.argmax(logits, dim=-1)[0].tolist()
        tokens = [self.inv.get(i, "<unk>") for i in ids]
        out: list[dict] = []
        frame = 0
        for token, group in groupby(tokens):
            n = len(list(group))
            start, frame = frame, frame + n
            if token == self.pad or token == self.delim:
                continue
            out.append(
                {
                    "sym": token,
                    "t0": start * self.stride / rate,
                    "t1": frame * self.stride / rate,
                }
            )
        return out


def cut_words(heard: list[dict], words: list[str], times: dict) -> list[dict]:
    """Per-word reference sounds, by which mark window each symbol's middle sits in."""
    out = []
    for i, word in enumerate(words):
        t0 = times.get(f"w{i}")
        t1 = times.get(f"w{i + 1}", times.get("end"))
        if t0 is None or t1 is None:
            out.append({"word": word, "phone": "", "t0": None, "t1": None})
            continue
        syms = [s["sym"] for s in heard if t0 <= (s["t0"] + s["t1"]) / 2 < t1]
        out.append(
            {"word": word, "phone": " ".join(syms), "t0": t0, "t1": t1}
        )
    return out


def best_anywhere(target: list[str], flat: list[str]) -> tuple[float, int, int]:
    """design/366's search: the best window anywhere in the whole run."""
    span = len(target)
    if not span or not flat:
        return 0.0, -1, -1
    best, at, size = 0.0, -1, 0
    for width in range(max(1, span - 1), span + 3):
        for start in range(0, max(1, len(flat) - width + 1)):
            got = overlap_ratio(target, flat[start : start + width])
            if got > best:
                best, at, size = got, start, width
    return best, at, size


def best_in_order(
    targets: list[list[str]], flat: list[str]
) -> list[tuple[float, int, int]]:
    """The same search, but each word may only start after the last one ended.

    This is the claim under test. Words come out of a mouth in the printed order,
    so once `film` is located the search for the word before it is bounded. A
    two-sound target then has a handful of places to sit instead of the whole
    sentence.
    """
    out: list[tuple[float, int, int]] = []
    cursor = 0
    total = sum(max(1, len(t)) for t in targets) or 1
    for i, target in enumerate(targets):
        span = len(target)
        if not span or cursor >= len(flat):
            out.append((0.0, -1, 0))
            continue
        # How far ahead this word may reasonably start: its own share of what is
        # left, doubled for slack, and never less than a few units.
        share = sum(max(1, len(t)) for t in targets[i:]) or 1
        room = int((len(flat) - cursor) * (max(1, span) / share) * 2) + 4
        window = flat[cursor : cursor + room]
        best, at, size = best_anywhere(target, window)
        out.append((best, cursor + at if at >= 0 else -1, size))
        if at >= 0 and best >= _OVERLAP_MIN:
            cursor = cursor + at + max(1, size)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/ctc_ref_probe.json")
    ap.add_argument("--voice", default="en-US-Neural2-D")
    args = ap.parse_args()

    hearer = Hearer()
    refs: list[dict] = []
    for sentence in SENTENCES:
        raw, times = synthesize_with_timepoints(sentence, args.voice)
        pcm, rate = pcm_from_wav(raw)
        heard = hearer.hear(pcm, rate)
        _ssml, words = ssml_with_marks(sentence)
        refs.append(
            {
                "sentence": sentence,
                "seconds": round(len(pcm) / rate, 3),
                "mark_n": len(times),
                "word_n": len(words),
                "run": " ".join(s["sym"] for s in heard),
                "words": cut_words(heard, words, times),
            }
        )
        print(
            f"synth ok words={len(words)} marks={len(times)} "
            f"secs={len(pcm) / rate:.2f} syms={len(heard)}"
        )

    # The claim. Positive = the word against the run of its own sentence, which
    # is a read that cannot be wrong. Negative = against another sentence's run,
    # which the speaker never said.
    modes = {"anywhere": {}, "in_order": {}}
    rows: list[dict] = []
    for ri, ref in enumerate(refs):
        targets = [split_phone_units(w["phone"]) for w in ref["words"]]
        for role, other in (("positive", ri), ("negative", (ri + 1) % len(refs))):
            flat = split_phone_units(refs[other]["run"])
            anywhere = [best_anywhere(t, flat) for t in targets]
            ordered = best_in_order(targets, flat)
            for wi, word in enumerate(ref["words"]):
                units = len(targets[wi])
                rows.append(
                    {
                        "sentence_i": ri,
                        "word": word["word"],
                        "units": units,
                        "role": role,
                        "anywhere": round(anywhere[wi][0], 4),
                        "in_order": round(ordered[wi][0], 4),
                        "short": 1 if units < _MIN_PHONES else 0,
                    }
                )
    for row in rows:
        for mode in ("anywhere", "in_order"):
            bucket = modes[mode].setdefault(
                (row["role"], "short" if row["short"] else "long"),
                {"n": 0, "pass": 0},
            )
            bucket["n"] += 1
            if row[mode] >= _OVERLAP_MIN:
                bucket["pass"] += 1

    print(f"\nthreshold={_OVERLAP_MIN} min_units={_MIN_PHONES}")
    print(f"{'mode':<10}{'role':<10}{'len':<7}{'pass/n':>10}{'rate':>8}")
    report = {}
    for mode in ("anywhere", "in_order"):
        for key, bucket in sorted(modes[mode].items()):
            rate = bucket["pass"] / bucket["n"] if bucket["n"] else 0.0
            print(
                f"{mode:<10}{key[0]:<10}{key[1]:<7}"
                f"{bucket['pass']:>5}/{bucket['n']:<4}{rate:>8.1%}"
            )
            report[f"{mode}|{key[0]}|{key[1]}"] = {
                "pass": bucket["pass"], "n": bucket["n"], "rate": round(rate, 4)
            }

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "model": MODEL,
                "voice": args.voice,
                "threshold": _OVERLAP_MIN,
                "min_units": _MIN_PHONES,
                "summary": report,
                "rows": rows,
                "refs": refs,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
