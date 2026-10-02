"""design/380 - when two readings disagree about a sound, was the model unsure?

`voice_gap_probe.py` found that two correct readings of the same sentence disagree
on about 3% of sounds, and that the disagreements are things like the open vowel
standing in for the near-open one. That raises the obvious question: the slower
reading is the *same voice saying the same words*, so is the vowel really different,
or is the model flipping a coin at the edge of its own decision?

The two answers want opposite things:

  real       Slower speech genuinely has fuller vowels. Then the disagreement is
             information, and the scorer is right to count it.

  unsure     The model gives the two candidates nearly equal scores and the winner
             changes with any nudge. Then the disagreement is noise, the scorer is
             counting a coin flip against the reader, and sounds the model is not
             sure about should not be decided by a hair.

`phone_frames` keeps only the winner, so this re-runs the model and keeps the
probabilities. For every sound it records how sure the model was, and what it
thought was second best. Then it lines the two readings up and compares the
confidence where they agree against the confidence where they do not.

Symbols print as escaped codepoints.

Usage:
    python scripts/sound_doubt_probe.py
    python scripts/sound_doubt_probe.py --rate 0.8
"""
from __future__ import annotations

import argparse
import pathlib
import statistics as stat
import sys
from itertools import groupby
from xml.sax.saxutils import escape

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

SENTENCES = [
    "The catalyst was prepared by chemical vapor deposition.",
    "Nanoparticles were dispersed on the carbon support.",
    "We measured the electrochemical surface area after cycling.",
    "Figure two shows the current density against potential.",
    "The result was reproduced in three independent runs.",
]


def esc(sym: str) -> str:
    return sym.encode("unicode_escape").decode("ascii") if sym else "-"


def sounds_with_doubt(
    text: str, voice: str, rate: str | None
) -> list[tuple[str, float, str, float]]:
    """Each sound the model emits, with how sure it was and its runner-up."""
    import torch

    from sentence_reading.llm import hear_waveform as hw
    from sentence_reading.llm import sound_reference as sr

    body = escape(text)
    ssml = (
        f"<speak><prosody rate='{rate}'>{body}</prosody></speak>"
        if rate
        else f"<speak>{body}</speak>"
    )
    raw, _t = sr.synth_marked(ssml, voice)
    pcm, _rate = sr.pcm_of(raw)

    hw._load_frames()
    hw._load_ctc()
    with hw._LOCK:
        values = hw._EXTRACTOR(
            pcm, sampling_rate=16000, return_tensors="pt"
        ).input_values
        with torch.no_grad():
            logits = hw._MODEL(values).logits[0]
    probs = torch.softmax(logits, dim=-1)
    ids = logits.argmax(dim=-1).tolist()

    out: list[tuple[str, float, str, float]] = []
    frame = 0
    for tid, group in groupby(ids):
        n = sum(1 for _ in group)
        f0, frame = frame, frame + n
        if tid == hw._PAD:
            continue
        sym = hw._INV.get(int(tid), "")
        if not sym:
            continue
        # Average over the frames this sound was emitted on, so one wobbly frame
        # inside a long steady sound does not stand for the whole thing.
        window = probs[f0:frame]
        mine = float(window[:, tid].mean())
        # Second best, excluding this symbol and the blank.
        avg = window.mean(dim=0).clone()
        avg[tid] = -1.0
        avg[hw._PAD] = -1.0
        other = int(avg.argmax())
        out.append((sym, mine, hw._INV.get(other, ""), float(avg[other])))
    return out


def align(left: list[str], right: list[str]) -> list[tuple[int, int]]:
    """Cheapest pairing of the two sequences, as index pairs (-1 for a gap)."""
    n, m = len(left), len(right)
    cost = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        cost[i][0] = i
    for j in range(m + 1):
        cost[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            same = left[i - 1] == right[j - 1]
            cost[i][j] = min(
                cost[i - 1][j - 1] + (0 if same else 1),
                cost[i - 1][j] + 1,
                cost[i][j - 1] + 1,
            )
    pairs: list[tuple[int, int]] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i and j and cost[i][j] == cost[i - 1][j - 1] + (
            0 if left[i - 1] == right[j - 1] else 1
        ):
            pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif i and cost[i][j] == cost[i - 1][j] + 1:
            pairs.append((i - 1, -1))
            i -= 1
        else:
            pairs.append((-1, j - 1))
            j -= 1
    pairs.reverse()
    return pairs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rate", default="0.8")
    ap.add_argument("--other-voice", default="")
    ap.add_argument("--sentences", type=int, default=len(SENTENCES))
    args = ap.parse_args()

    from sentence_reading.llm import sound_reference as sr

    voice = sr.reference_voice()
    if args.other_voice:
        print(f"comparing {voice} against {args.other_voice}, both at normal speed")
    else:
        print(f"comparing {voice} at normal speed against the same voice at "
              f"rate {args.rate}")
    print()

    agree_conf: list[float] = []
    differ_conf: list[float] = []
    runner_up_was_it = 0
    differ: list[tuple[str, float, str, str, float, str]] = []
    gaps = n_agree = 0

    for text in SENTENCES[: max(1, args.sentences)]:
        a = sounds_with_doubt(text, voice, None)
        if args.other_voice:
            b = sounds_with_doubt(text, args.other_voice, None)
        else:
            b = sounds_with_doubt(text, voice, args.rate)
        pairs = align([s for s, _c, _o, _oc in a], [s for s, _c, _o, _oc in b])
        for i, j in pairs:
            if i < 0 or j < 0:
                gaps += 1
                continue
            sym_a, conf_a, up_a, _ua = a[i]
            sym_b, conf_b, up_b, _ub = b[j]
            if sym_a == sym_b:
                n_agree += 1
                agree_conf.append(conf_a)
                agree_conf.append(conf_b)
                continue
            differ_conf.append(conf_a)
            differ_conf.append(conf_b)
            if (up_a == sym_b) or (up_b == sym_a):
                runner_up_was_it += 1
            differ.append((sym_a, conf_a, up_a, sym_b, conf_b, up_b))

    print(f"agreed on {n_agree} sounds, disagreed on {len(differ)}, "
          f"one side had a sound the other did not {gaps} times")
    print()
    if agree_conf:
        print(f"how sure the model was where the two agreed : "
              f"{stat.mean(agree_conf):.3f} (median {stat.median(agree_conf):.3f})")
    if differ_conf:
        print(f"how sure the model was where they disagreed : "
              f"{stat.mean(differ_conf):.3f} (median {stat.median(differ_conf):.3f})")
        print(f"the other reading\'s sound was the runner-up : "
              f"{runner_up_was_it}/{len(differ)}")
        sure = sum(1 for c in differ_conf if c >= 0.70)
        print(f"disagreements where the model was over 0.70 sure: "
              f"{sure}/{len(differ_conf)}")
    print()
    if differ:
        print("first reading           second reading")
        print("sound  sure  2nd        sound  sure  2nd")
        for sym_a, conf_a, up_a, sym_b, conf_b, up_b in differ[:20]:
            print(f"{esc(sym_a):6s} {conf_a:.2f}  {esc(up_a):9s}  "
                  f"{esc(sym_b):6s} {conf_b:.2f}  {esc(up_b):9s}")
    print()
    print("reading: if the two columns are unsure and each has the other\'s sound as")
    print("its runner-up, the disagreement is the model hesitating, not two")
    print("different pronunciations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
