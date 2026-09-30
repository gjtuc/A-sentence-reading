"""Does the minimum catch a word read as its near neighbour?

A frame's probabilities sum to one, so `ui` and `oU` do not share a score. If
the speaker says `grow` where `grew` was printed, the `ui` column has to fall
and the minimum has to see it. That is the claim. It has not been tested, and
the 122 words no score caught are exactly the near-miss cases, so it matters.

There is a natural experiment in the corpus. One learner read a `grew` sentence
33 times across all ten speeds. The transcript wrote `grew` 29 times and `grow`
4 times. Same speaker, same word, both labels. So:

* synthesize the sentence as printed         -> what a right reading scores
* synthesize it with the neighbour swapped   -> what a real mistake scores
* score all 33 real takes                    -> where the person actually sits

Every take is also scored against the neighbour's own reference. If the person
said `grow`, the `grow` reference must fit better than the `grew` one. That is
the speaker's own logic, asked of the model directly.

    python scripts/neighbor_swap_probe.py
"""

from __future__ import annotations

import collections
import json
import pathlib
import statistics as stat
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from sentence_reading.llm.phone_match import split_phone_units  # noqa: E402
from ctc_reference_probe import pcm_from_wav  # noqa: E402
from cross_voice_probe import READ_VOICE, REF_VOICE, synth_voice  # noqa: E402
from ctc_prob_score_probe import logprobs, nm, sure_per_word  # noqa: E402
from human_takes_probe import (  # noqa: E402
    BREAK,
    PAD,
    TAKES,
    bare,
    cut_tokens,
    hand_out_loose,
    pcm_of,
    ssml_every,
)

import importlib  # noqa: E402

wide = importlib.import_module("timing_spread_probe")

OUT = pathlib.Path(".cache/neighbor_swap.json")

# The printed word, and the word the transcript claims was said instead. Both
# came out of the 122 words no score caught.
CASES = [
    ("grew", "grow"),
    ("fed", "fat"),
]


def reference(m, sentence: str) -> list[tuple[str, list[str]]]:
    """One token, one list of sounds. The design/371 build, no shortcuts."""
    flat_raw, _t = synth_voice(f"<speak>{sentence}</speak>", REF_VOICE)
    pcm0, rate0 = pcm_from_wav(flat_raw)
    natural = [s["sym"] for s in m.run(pcm0, rate0)]
    ssml, tokens = ssml_every(sentence, BREAK)
    raw, times = synth_voice(ssml, REF_VOICE)
    pcm, rate = pcm_from_wav(raw)
    clean = cut_tokens(
        m, m.run(pcm, rate), tokens, times, rate, PAD, len(pcm) / rate
    )
    given = hand_out_loose([list(u) for _w, u in clean], natural)
    return [(w, given[i]) for i, (w, _u) in enumerate(clean)]


def score_word(m, pcm, rate, ref, which: int):
    """What the scorer says about one token of one reading."""
    sheet = logprobs(m, pcm, rate)
    sure = sure_per_word(m, sheet, [list(u) for _w, u in ref])
    if sure[which] is None:
        return None
    cert, f0, f1, certs = sure[which]
    heard = m.run(pcm, rate)
    here = [s for s in heard if f0 <= (s["f0"] + s["f1"]) / 2 < f1]
    extra = max(0, len(here) - len(certs))
    return {
        "sure": cert,
        "worst": min(certs),
        "full": cert - extra / len(certs),
        "certs": [round(c, 4) for c in certs],
    }


def find(ref, word: str) -> int:
    for i, (token, _u) in enumerate(ref):
        if bare(token) == word:
            return i
    return -1


def takes_for(word: str) -> list[dict]:
    """Every take whose printed line carries the word."""
    out = []
    for path in sorted(TAKES.glob("*.json")):
        one = json.loads(path.read_text(encoding="utf-8"))
        text = (one.get("expected") or "")
        if word not in text.lower():
            continue
        if not (TAKES / f"{one['stem']}.m4a").exists():
            continue
        out.append(one)
    return out


def run_case(m, word: str, wrong: str) -> dict:
    cards = takes_for(word)
    print(f"\n=== {word} vs {wrong}: {len(cards)} real takes")
    lines = sorted({(c["expected"] or "").strip() for c in cards})

    right_ref, wrong_ref, at_right, at_wrong = {}, {}, {}, {}
    for line in lines:
        swapped = line.replace(word, wrong).replace(
            word.capitalize(), wrong.capitalize()
        )
        try:
            right_ref[line] = reference(m, line)
            wrong_ref[line] = reference(m, swapped)
        except Exception as exc:  # noqa: BLE001
            print(f"  skip line ({type(exc).__name__})")
            continue
        at_right[line] = find(right_ref[line], word)
        at_wrong[line] = find(wrong_ref[line], wrong)
        if at_right[line] < 0 or at_wrong[line] < 0:
            print(f"  cannot place the word in {line[:40]!r}")
            right_ref.pop(line), wrong_ref.pop(line)
    print(f"  built {len(right_ref)} reference pairs for {len(lines)} lines")

    pick = max(right_ref, key=lambda s: len(s)) if right_ref else None
    machine = {}
    if pick:
        ref, i = right_ref[pick], at_right[pick]
        print(f"  reference {word} = "
              f"{' '.join(nm(u) for u in split_phone_units(' '.join(ref[i][1])))}")
        for name, text in (("right", pick),
                           ("wrong", pick.replace(word, wrong))):
            raw, _t = synth_voice(f"<speak>{text}</speak>", READ_VOICE)
            p, r = pcm_from_wav(raw)
            got = score_word(m, p, r, ref, i)
            machine[name] = got
            if got:
                print(f"  machine reads {name:<5} -> worst {got['worst']:.3f}"
                      f"  sure {got['sure']:.3f}  each "
                      f"{[f'{c:.2f}' for c in got['certs']]}")

    rows = []
    for n, card in enumerate(cards, 1):
        line = (card["expected"] or "").strip()
        if line not in right_ref:
            continue
        try:
            pcm, rate = pcm_of(m, card["stem"])
        except Exception as exc:  # noqa: BLE001
            print(f"  skip take ({type(exc).__name__})")
            continue
        got = score_word(m, pcm, rate, right_ref[line], at_right[line])
        other = score_word(m, pcm, rate, wrong_ref[line], at_wrong[line])
        if not got or not other:
            continue
        said = bare_words(card.get("heard") or "")
        rows.append({
            "stem": card["stem"],
            "tier": card["skill_tier"],
            "label": word if word in said else (
                wrong if wrong in said else "neither"),
            "right_worst": got["worst"],
            "right_sure": got["sure"],
            "right_certs": got["certs"],
            "wrong_worst": other["worst"],
            "wrong_sure": other["sure"],
        })
        print(f"  {n:>3}/{len(cards)} tier {card['skill_tier']}"
              f" said={rows[-1]['label']:<8}"
              f" {word}-ref worst {got['worst']:.3f}"
              f"  {wrong}-ref worst {other['worst']:.3f}")

    show(word, wrong, machine, rows)
    return {"word": word, "wrong": wrong, "machine": machine, "takes": rows}


def bare_words(text: str) -> set[str]:
    return {bare(w) for w in (text or "").split()}


def show(word: str, wrong: str, machine: dict, rows: list[dict]) -> None:
    if not rows:
        return
    by = collections.defaultdict(list)
    for r in rows:
        by[r["label"]].append(r)
    print(f"\n  what the transcript said, against the {word} reference")
    print("  transcript  takes   worst avg   worst min   fits wrong ref better")
    for label in (word, wrong, "neither"):
        group = by.get(label) or []
        if not group:
            continue
        w = [r["right_worst"] for r in group]
        better = sum(1 for r in group if r["wrong_worst"] > r["right_worst"])
        print(f"  {label:<10} {len(group):>6}   {stat.mean(w):.3f}"
              f"       {min(w):.3f}       {better}/{len(group)}")
    if machine.get("wrong") and machine.get("right"):
        print(f"\n  for scale: the machine saying {wrong} scores"
              f" {machine['wrong']['worst']:.3f},"
              f" saying {word} scores {machine['right']['worst']:.3f}")
        floor = machine["wrong"]["worst"]
        under = sum(1 for r in rows if r["right_worst"] <= floor)
        print(f"  real takes at or under the machine mistake: {under}/{len(rows)}")


def main() -> int:
    m = wide.M()
    report = [run_case(m, word, wrong) for word, wrong in CASES]
    OUT.write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
