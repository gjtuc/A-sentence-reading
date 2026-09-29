"""design/371 - how exact are SSML mark times, measured against the audio?

`ctc_reference_probe.py` cut `is` down to one sound and `at` down to one. This
answers whether a sound went missing or landed in the wrong word, and whether
anything cheap fixes it.

Three checks, in the order they were needed:

* `shift` - where every symbol sits against every mark, plus what a constant
  offset would do. A constant offset is the obvious fix and this shows it is
  not one: a cut can look right by symbol count while holding the neighbour's
  sound, so counts are never the test. Content is.
* `bracket` - a mark on each side of the word instead of inferring the end from
  the next word's mark.
* `rate` - a slower voice, so a sound lasts longer against a fixed mark error.

`--truth` is hand-written from the run at rate 1.0 and is the pronunciation this
voice actually produced, not a dictionary's. It exists so a cut can be judged by
what is in it.

No IPA reaches the console; cp949 dies on it. Symbols go to the report.

    python scripts/mark_boundary_probe.py
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from ctc_reference_probe import Hearer, pcm_from_wav  # noqa: E402

SENT = "This effect is small at room temperature."
VOICE = "en-US-Neural2-D"

# What this voice says, read off the run at rate 1.0. Not a dictionary.
TRUTH = {
    "This": "ð ɪ s",
    "effect": "ᵻ f ɛ k t",
    "is": "ɪ z",
    "small": "s m ɔː l",
    "at": "æ t",
    "room": "ɹ uː m",
    "temperature": "t ɛ m p ɹ ɪ tʃ ɚ",
}
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")


def synth(ssml: str, rate: float) -> tuple[bytes, dict]:
    from google.cloud import texttospeech_v1beta1 as tts

    client = tts.TextToSpeechClient()
    ans = client.synthesize_speech(
        request=tts.SynthesizeSpeechRequest(
            input=tts.SynthesisInput(ssml=ssml),
            voice=tts.VoiceSelectionParams(language_code="en-US", name=VOICE),
            audio_config=tts.AudioConfig(
                audio_encoding=tts.AudioEncoding.LINEAR16,
                sample_rate_hertz=16000,
                speaking_rate=rate,
            ),
            enable_time_pointing=[
                tts.SynthesizeSpeechRequest.TimepointType.SSML_MARK
            ],
        )
    )
    return ans.audio_content, {
        p.mark_name: float(p.time_seconds) for p in ans.timepoints
    }


def build(bracket: bool) -> tuple[str, list[str]]:
    words = _WORD.findall(SENT)
    parts = ["<speak>"]
    for i, word in enumerate(words):
        if bracket:
            parts.append(f'<mark name="a{i}"/>{word}<mark name="b{i}"/> ')
        else:
            parts.append(f'<mark name="a{i}"/>{word} ')
    if not bracket:
        parts.append('<mark name="b_end"/>')
    parts.append("</speak>")
    return "".join(parts), words


def cut(heard, words, times, bracket: bool, shift: float = 0.0):
    """Each symbol goes to the word whose mark window holds its middle."""
    out = []
    for i, word in enumerate(words):
        t0 = times.get(f"a{i}")
        t1 = (
            times.get(f"b{i}")
            if bracket
            else times.get(f"a{i + 1}", times.get("b_end"))
        )
        if t0 is None or t1 is None:
            out.append((word, []))
            continue
        t0, t1 = t0 + shift, t1 + shift
        out.append(
            (word, [s["sym"] for s in heard if t0 <= (s["t0"] + s["t1"]) / 2 < t1])
        )
    return out


def hear_sentence(hearer: Hearer, bracket: bool, rate: float):
    ssml, words = build(bracket)
    raw, times = synth(ssml, rate)
    pcm, sr = pcm_from_wav(raw)
    return hearer.hear(pcm, sr), words, times, round(len(pcm) / sr, 3)


def score(got) -> list[str]:
    """The words whose cut does not hold exactly the sounds the voice made."""
    return [w for w, syms in got if " ".join(syms) != TRUTH[w]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=".cache/mark_boundary_report.json")
    args = ap.parse_args()

    hearer = Hearer()
    report: dict = {"sentence": SENT, "voice": VOICE, "truth": TRUTH}

    heard, words, times, secs = hear_sentence(hearer, bracket=False, rate=1.0)
    base = cut(heard, words, times, bracket=False)
    report["shift"] = {
        "seconds": secs,
        "marks": {k: round(v, 4) for k, v in times.items()},
        "symbols": [
            {"sym": s["sym"], "t0": round(s["t0"], 3), "t1": round(s["t1"], 3)}
            for s in heard
        ],
        "cuts": {w: " ".join(s) for w, s in base},
        "wrong": score(base),
        # A constant offset would show up as one shift that is right everywhere.
        "sweep": [
            {
                "shift_ms": ms,
                "wrong": score(cut(heard, words, times, False, ms / 1000.0)),
                "cuts": {
                    w: " ".join(s)
                    for w, s in cut(heard, words, times, False, ms / 1000.0)
                },
            }
            for ms in range(-80, 81, 20)
        ],
    }
    print(f"rate=1.0 bracket=no   secs={secs} syms={len(heard)} "
          f"wrong={len(report['shift']['wrong'])}/{len(words)} "
          f"{','.join(report['shift']['wrong']) or '-'}")

    report["variants"] = []
    for bracket in (False, True):
        for rate in (1.0, 0.7):
            if not bracket and rate == 1.0:
                continue
            h2, w2, t2, s2 = hear_sentence(hearer, bracket, rate)
            got = cut(h2, w2, t2, bracket)
            wrong = score(got)
            report["variants"].append(
                {
                    "bracket": bracket,
                    "rate": rate,
                    "seconds": s2,
                    "symbols": len(h2),
                    "assigned": sum(len(s) for _w, s in got),
                    "run": " ".join(s["sym"] for s in h2),
                    "cuts": {w: " ".join(s) for w, s in got},
                    "wrong": wrong,
                }
            )
            print(
                f"rate={rate} bracket={'yes' if bracket else 'no':<4} secs={s2} "
                f"syms={len(h2)} assigned={sum(len(s) for _w, s in got)} "
                f"wrong={len(wrong)}/{len(w2)} {','.join(wrong) or '-'}"
            )

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
