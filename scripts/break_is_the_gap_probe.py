"""The gap a closing mark reports is the break, not the word's own space.

With a 1ms break between words, every word end came back and every gap measured
exactly 5ms: 73 of 73, same to the millisecond. A real space between words would
vary. And the audio came out about 60ms per word shorter, which is roughly the
space the model's own timings said was there.

So one of two things is happening, and they lead to the same place. Either the
closing mark is reported mechanically as the next mark minus the break, in which
case it carries no information, or the break genuinely replaced the natural space,
in which case the mark is honest but the space it was supposed to measure is gone.

Sweeping the break settles it. If the gap tracks the break, the number is the break
and nothing else: asking how wide the space is destroys the space.
"""
from __future__ import annotations

import json
import pathlib
import re
import statistics as stat
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from ctc_reference_probe import pcm_from_wav  # noqa: E402
from cross_voice_probe import REF_VOICE, synth_voice  # noqa: E402

_WORD = re.compile(r"[A-Za-z']+")
SENTENCES = [
    "The light passes through the water without loss.",
    "This effect is small at room temperature.",
]
BREAKS = [None, 1, 20, 60, 100]


def build(sentence: str, ms):
    words = _WORD.findall(sentence)
    parts = ["<speak>"]
    for i, word in enumerate(words):
        parts.append(f'<mark name="w{i}"/>{word}')
        if ms is not None:
            parts.append(f'<mark name="e{i}"/><break time="{ms}ms"/>')
        parts.append(" ")
    parts.append("</speak>")
    return "".join(parts), words


def main() -> int:
    rows = []
    print(f"{'break':>7}{'ends got':>10}{'gap mean':>10}{'gap min':>9}"
          f"{'gap max':>9}{'audio':>9}{'per word':>10}")
    for sent in SENTENCES:
        base_len = None
        for ms in BREAKS:
            ssml, words = build(sent, ms)
            raw, times = synth_voice(ssml, REF_VOICE)
            pcm, rate = pcm_from_wav(raw)
            seconds = len(pcm) / rate
            if ms is None:
                base_len = seconds
                print(f"{'none':>7}{0:>5}/{len(words):<4}{'-':>10}{'-':>9}"
                      f"{'-':>9}{seconds:>8.2f}s{'base':>10}")
                rows.append({"sentence": sent[:24], "break": None,
                             "ends": 0, "seconds": round(seconds, 3)})
                continue
            gaps = [
                (times[f"w{i + 1}"] - times[f"e{i}"]) * 1000
                for i in range(len(words) - 1)
                if f"e{i}" in times and f"w{i + 1}" in times
            ]
            ends = sum(1 for i in range(len(words)) if f"e{i}" in times)
            per = (seconds - base_len) / len(words) * 1000
            print(f"{ms:>5}ms{ends:>5}/{len(words):<4}"
                  f"{stat.mean(gaps):>9.0f}ms{min(gaps):>8.0f}ms"
                  f"{max(gaps):>8.0f}ms{seconds:>8.2f}s{per:>+9.0f}ms")
            rows.append({
                "sentence": sent[:24], "break": ms, "ends": ends,
                "words": len(words), "gap_mean": round(stat.mean(gaps), 1),
                "gap_min": round(min(gaps), 1), "gap_max": round(max(gaps), 1),
                "seconds": round(seconds, 3), "per_word_ms": round(per, 1),
            })
        print()

    tracked = [r for r in rows if r["break"] and
               abs(r["gap_mean"] - r["break"]) <= 6 and
               r["gap_max"] - r["gap_min"] <= 2]
    print(f"gaps that just echo the break asked for: {len(tracked)}/"
          f"{sum(1 for r in rows if r['break'])}")
    print("if that is all of them, the closing mark measures the break and "
          "nothing about the word.")

    pathlib.Path(".cache/break_is_the_gap.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nwrote .cache/break_is_the_gap.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
