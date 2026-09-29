"""Can a mark be put on the space, so it reports where the word ended?

A mark placed right after a word came back with the same time as the next word's
mark, and one of the two was dropped. The suspicion is that a mark does not report
where it sits; it reports where the audio after it begins. If that is the rule
then no placement inside the space can give a word's end, because the audio after
the space is the next word either way.

There is one way around it. A mark cannot see a space, but it can see a `break`.
Put a break between the closing mark and the next opening mark and the two have
audible content between them, so the closing mark should land on the end of the
word instead of the start of the next one.

That is only useful if the break leaves the speech alone. A reference has to be
ordinary connected speech: synthesising words on their own already proved useless,
because this voice says `at` as `a d` alone and `ae t` in a sentence. So every
variant is checked against the plain reading twice, on the audio bytes and on the
symbol run, and a variant that moves either one is no use however many marks it
returns.

  plain   - marks before words only, today's form
  ends    - a closing mark right after each word
  spaced  - the closing mark moved past the space
  b0      - a zero length break between the two marks
  b1      - a one millisecond break
  bnone   - break strength none, which asks for no pause at all
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from ctc_reference_probe import pcm_from_wav  # noqa: E402
from cross_voice_probe import REF_VOICE, synth_voice  # noqa: E402

import importlib  # noqa: E402

wide = importlib.import_module("timing_spread_probe")

_WORD = re.compile(r"[A-Za-z']+")

SENTENCES = [
    "The light passes through the water without loss.",
    "This effect is small at room temperature.",
    "The film grew at five hundred degrees.",
]

# name -> what goes between the word and the next word's opening mark
BETWEEN = {
    "plain": None,
    "ends": '<mark name="e{i}"/> ',
    "spaced": ' <mark name="e{i}"/> ',
    "b0": '<mark name="e{i}"/><break time="0ms"/> ',
    "b1": '<mark name="e{i}"/><break time="1ms"/> ',
    "bnone": '<mark name="e{i}"/><break strength="none"/> ',
}


def build(sentence: str, kind: str) -> tuple[str, list[str]]:
    words = _WORD.findall(sentence)
    tail = BETWEEN[kind]
    parts = ["<speak>"]
    for i, word in enumerate(words):
        parts.append(f'<mark name="w{i}"/>{word}')
        parts.append(" " if tail is None else tail.format(i=i))
    parts.append("</speak>")
    return "".join(parts), words


def main() -> int:
    m = wide.M()
    rows = []
    print(f"{'sentence':<9}{'variant':<9}{'ends got':>10}{'audio':>8}"
          f"{'sounds':>8}{'starts move':>13}")
    for si, sent in enumerate(SENTENCES):
        base = None
        for kind in BETWEEN:
            ssml, words = build(sent, kind)
            raw, times = synth_voice(ssml, REF_VOICE)
            pcm, rate = pcm_from_wav(raw)
            run = [s["sym"] for s in m.run(pcm, rate)]
            starts = [times.get(f"w{i}") for i in range(len(words))]
            ends = sum(1 for i in range(len(words)) if f"e{i}" in times)
            digest = hashlib.md5(raw).hexdigest()[:8]
            if kind == "plain":
                base = {"digest": digest, "run": run, "starts": starts}
                same_audio, same_run, moved = "base", "base", "base"
            else:
                same_audio = "same" if digest == base["digest"] else "CHANGED"
                same_run = "same" if run == base["run"] else "CHANGED"
                drift = [
                    abs(a - b) * 1000
                    for a, b in zip(starts, base["starts"])
                    if a is not None and b is not None
                ]
                moved = f"{max(drift):.0f}ms" if drift else "-"
            print(f"{si:<9}{kind:<9}{ends:>4}/{len(words):<5}{same_audio:>8}"
                  f"{same_run:>8}{moved:>13}")
            rows.append({
                "sentence": si, "variant": kind, "words": len(words),
                "ends_returned": ends, "marks_returned": len(times),
                "audio": same_audio, "run": same_run, "starts_moved": moved,
                "sounds": len(run),
            })
        print()

    good = [
        r for r in rows
        if r["variant"] != "plain"
        and r["ends_returned"] == r["words"]
        and r["audio"] == "same"
    ]
    print(f"variants that give every word end without touching the audio: "
          f"{len(good)}")
    for r in good:
        print(f"   sentence {r['sentence']} {r['variant']}")
    kept_run = [
        r for r in rows
        if r["variant"] != "plain"
        and r["ends_returned"] == r["words"]
        and r["run"] == "same"
    ]
    print(f"variants that give every word end with the same sounds: "
          f"{len(kept_run)}")
    for r in kept_run:
        print(f"   sentence {r['sentence']} {r['variant']} "
              f"(audio {r['audio']}, starts moved {r['starts_moved']})")

    pathlib.Path(".cache/mark_in_space_report.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print("\nwrote .cache/mark_in_space_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
