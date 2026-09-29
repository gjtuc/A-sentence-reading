"""Does a widened reference still score? Tested across two different voices.

Widening was going to cost something. A reference for `small` that carries the
`z` off the end of `is` has six sounds where four belong, and four matched out of
six is 0.67, under the line. That was the worry.

It may not be a worry at all. The reader reads the same sentence, so the reader's
run holds that `z` too, and the compare searches the whole run. The contamination
is on both sides, which means it cancels. That has to be measured rather than
argued.

The reference is built from one voice. The reading is a different voice saying
the same sentence, which is the closest thing here to another speaker: not the
same audio, so a match is not guaranteed the way it was when a reference was
compared against the file it was cut from. The negative is that other voice
reading a different sentence.
"""
from __future__ import annotations

import json
import pathlib
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

import importlib  # noqa: E402

wide = importlib.import_module("timing_spread_probe")

REF_VOICE = "en-US-Neural2-D"
READ_VOICE = "en-US-Neural2-F"
PADS = [0, 25]
SENTENCES = [
    "The film grew at five hundred degrees.",
    "The catalyst was prepared by chemical vapour deposition.",
    "We measured the dispersion of the nanoparticles in water.",
    "This effect is small at room temperature.",
    "The single cell performance was stable for one hundred hours.",
]


def synth_voice(ssml: str, voice: str):
    from google.cloud import texttospeech_v1beta1 as tts

    client = tts.TextToSpeechClient()
    ans = client.synthesize_speech(
        request=tts.SynthesizeSpeechRequest(
            input=tts.SynthesisInput(ssml=ssml),
            voice=tts.VoiceSelectionParams(language_code="en-US", name=voice),
            audio_config=tts.AudioConfig(
                audio_encoding=tts.AudioEncoding.LINEAR16, sample_rate_hertz=16000
            ),
            enable_time_pointing=[
                tts.SynthesizeSpeechRequest.TimepointType.SSML_MARK
            ],
        )
    )
    return ans.audio_content, {
        p.mark_name: float(p.time_seconds) for p in ans.timepoints
    }


def main() -> int:
    m = wide.M()
    refs, reads = [], []
    for sent in SENTENCES:
        ssml, words = ssml_with_marks(sent)
        raw, times = synth_voice(ssml, REF_VOICE)
        pcm, rate = pcm_from_wav(raw)
        heard = m.run(pcm, rate)
        cuts = {}
        for pad in PADS:
            p = pad / 1000.0
            per = []
            for i, word in enumerate(words):
                t0 = times[f"w{i}"] - p
                t1 = times.get(f"w{i + 1}", times["end"]) + p
                per.append(
                    (word, " ".join(
                        s["sym"] for s in heard
                        if t0 <= (m.s(s["f0"], rate) + m.s(s["f1"], rate)) / 2 < t1
                    ))
                )
            cuts[pad] = per
        refs.append({"sentence": sent, "cuts": cuts})

        r_raw, _t = synth_voice(f"<speak>{sent}</speak>", READ_VOICE)
        r_pcm, r_rate = pcm_from_wav(r_raw)
        reads.append(" ".join(s["sym"] for s in m.run(r_pcm, r_rate)))
        print(f"built: {sent[:38]:<38} ref_syms={len(heard)}")

    print(f"\nreference voice {REF_VOICE}, reading voice {READ_VOICE}")
    print(f"threshold {_OVERLAP_MIN}, floor {_MIN_PHONES} sounds")
    print(f"{'pad':>4}{'role':<10}{'len':<7}{'pass/n':>10}{'rate':>8}{'mean_ratio':>12}")
    summary, rows = {}, []
    for pad in PADS:
        buckets: dict[tuple, dict] = {}
        for ri, ref in enumerate(refs):
            for role, other in (("read_same", ri), ("read_other", (ri + 1) % len(refs))):
                flat = split_phone_units(reads[other])
                for word, phone in ref["cuts"][pad]:
                    units = split_phone_units(phone)
                    ratio = best_window_overlap(units, flat) if units else 0.0
                    judged = len(units) >= _MIN_PHONES
                    key = (role, "judged" if judged else "too_short")
                    b = buckets.setdefault(key, {"n": 0, "pass": 0, "sum": 0.0})
                    b["n"] += 1
                    b["sum"] += ratio
                    if judged and ratio >= _OVERLAP_MIN:
                        b["pass"] += 1
                    rows.append({
                        "pad": pad, "role": role, "word": word, "units": len(units),
                        "ratio": round(ratio, 3), "judged": judged,
                    })
        for key in sorted(buckets):
            b = buckets[key]
            rate = b["pass"] / b["n"] if b["n"] else 0.0
            print(f"{pad:>4}{key[0]:<10}{key[1]:<7}{b['pass']:>5}/{b['n']:<4}"
                  f"{rate:>8.1%}{b['sum'] / b['n']:>12.3f}")
            summary[f"{pad}|{key[0]}|{key[1]}"] = {
                "pass": b["pass"], "n": b["n"], "rate": round(rate, 3),
                "mean_ratio": round(b["sum"] / b["n"], 3),
            }

    pathlib.Path(".cache/cross_report.json").write_text(
        json.dumps({"summary": summary, "rows": rows, "refs": refs, "reads": reads},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print("\nwrote .cache/cross_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
