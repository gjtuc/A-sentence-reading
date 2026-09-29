"""Cut the reference at the quiet, then hand out the take in the same order.

Two ideas, and the second is the one that pays.

First, the mark is the wrong place to cut the reference. The mark says where the
word's audio starts, but the model's symbol for that sound fires about 40ms
later, so cutting at the mark drops the boundary inside the previous word's
trailing sound. The 25ms pad was covering for that. A pad is a guess; the quiet
between two words is a fact, and its middle is a boundary that needs no constant.
Cutting there makes the words partition the run: no overlap, no leftovers, order
intact.

  flat - the 25ms pad both sides, for comparison
  tile - boundary at the middle of the widest quiet near the mark

Second, the take has no marks, so a word still has to be searched for. But once
the reference words are a clean ordered sequence, the search can be ordered too,
and then every sound in the take belongs to exactly one word. That is what fixes
`loss` scoring 1.00 against someone who said `lost`: today the search stops
before the `t` and never sees it. If the take is handed out in order, the `t` has
to go somewhere, and it sits far closer to `los` than to the next word, so it
lands on `loss` and counts as the extra sound it is.

  anywhere  - best stretch in the whole take, each word on its own. Today's rule.
  ordered   - the take is split into one stretch per word, in order, and the word
              is scored against its stretch loosely, best sub-stretch wins
  partition - same split, but scored end to end, so a sound the reader added
              costs the same as one they dropped

`slot_direct` is the ceiling: the take's own marks decide the regions. Real takes
have no marks, so it cannot be built, but it says how much the ordered search
gives up by having to guess.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from sentence_reading.llm.phone_match import (  # noqa: E402
    _MIN_PHONES,
    _OVERLAP_MIN,
    best_window_overlap,
    overlap_ratio,
    split_phone_units,
)
from ctc_reference_probe import pcm_from_wav, ssml_with_marks  # noqa: E402
from cross_voice_probe import READ_VOICE, REF_VOICE, synth_voice  # noqa: E402
from one_word_wrong_probe import SWAPS  # noqa: E402

import importlib  # noqa: E402

wide = importlib.import_module("timing_spread_probe")

PAD = 0.025
# How far from the mark a boundary may sit. The lag runs 20 to 60ms, so the quiet
# that belongs to a mark is usually a little after it, rarely before.
BACK, FORWARD = 0.060, 0.100


def flat(m, heard, words, times, rate):
    out = []
    for i, word in enumerate(words):
        lo = times[f"w{i}"] - PAD
        hi = times.get(f"w{i + 1}", times["end"]) + PAD
        out.append((word, [
            s["sym"] for s in heard
            if lo <= (m.s(s["f0"], rate) + m.s(s["f1"], rate)) / 2 < hi
        ]))
    return out


def tile(m, heard, words, times, rate):
    """Words take neighbouring slices of the run, split at the widest quiet."""
    n = len(heard)
    if not n:
        return [(w, []) for w in words]
    t0 = [m.s(s["f0"], rate) for s in heard]
    t1 = [m.s(s["f1"], rate) for s in heard]
    quiet = [0.0] + [max(0.0, t0[k] - t1[k - 1]) for k in range(1, n)]
    middle = [t0[0]] + [(t1[k - 1] + t0[k]) / 2 for k in range(1, n)]

    cuts = [0]
    for i in range(1, len(words)):
        mark = times[f"w{i}"]
        pick, best = None, None
        for k in range(cuts[-1], n):
            if middle[k] < mark - BACK:
                continue
            if middle[k] > mark + FORWARD:
                break
            # Widest quiet wins; ties go to the boundary nearer the mark.
            key = (quiet[k], -abs(middle[k] - mark))
            if best is None or key > best:
                pick, best = k, key
        if pick is None:
            pick = next((k for k in range(cuts[-1], n) if t0[k] >= mark), n)
        cuts.append(max(pick, cuts[-1]))
    cuts.append(n)
    return [
        (word, [heard[k]["sym"] for k in range(cuts[i], cuts[i + 1])])
        for i, word in enumerate(words)
    ]


def units(syms) -> list[str]:
    return split_phone_units(" ".join(syms))


def hand_out(refs: list[list[str]], take: list[str]) -> list[list[str]]:
    """Give every sound in the take to exactly one word, keeping word order.

    The split that scores highest overall wins. A word gains nothing by taking a
    sound that is not its own, because the score divides by the longer of the two
    sides, so a grabbed sound lowers the grabber.
    """
    n, m = len(refs), len(take)
    neg = float("-inf")
    best = [[neg] * (m + 1) for _ in range(n + 1)]
    back = [[0] * (m + 1) for _ in range(n + 1)]
    best[0][0] = 0.0
    for i in range(1, n + 1):
        ref = refs[i - 1]
        widest = min(m, 2 * len(ref) + 4)
        for j in range(m + 1):
            for width in range(0, widest + 1):
                k = j - width
                if k < 0 or best[i - 1][k] == neg:
                    continue
                got = best[i - 1][k]
                if width:
                    got += overlap_ratio(ref, take[k:j])
                if got > best[i][j]:
                    best[i][j] = got
                    back[i][j] = k
    if best[n][m] == neg:
        return [list(take) if i == 0 else [] for i in range(n)]
    out: list[list[str]] = [[] for _ in range(n)]
    j = m
    for i in range(n, 0, -1):
        k = back[i][j]
        out[i - 1] = take[k:j]
        j = k
    return out


def main() -> int:
    m = wide.M()

    refs = {}
    for sent in SWAPS:
        ssml, words = ssml_with_marks(sent)
        raw, times = synth_voice(ssml, REF_VOICE)
        pcm, rate = pcm_from_wav(raw)
        heard = m.run(pcm, rate)
        refs[sent] = {
            "flat": [(w, units(s)) for w, s in flat(m, heard, words, times, rate)],
            "tile": [(w, units(s)) for w, s in tile(m, heard, words, times, rate)],
        }
        print(f"ref   {sent[:44]}")

    cases = []
    for sent, pairs in SWAPS.items():
        for target, wrong in pairs:
            said = re.sub(rf"\b{target}\b", wrong, sent, count=1)
            ssml, said_words = ssml_with_marks(said)
            raw, times = synth_voice(ssml, READ_VOICE)
            pcm, rate = pcm_from_wav(raw)
            heard = m.run(pcm, rate)
            cases.append({
                "sentence": sent, "target": target, "wrong": wrong,
                "whole": units([s["sym"] for s in heard]),
                "slots": {w: units(s) for w, s in
                          flat(m, heard, said_words, times, rate)},
            })
    print(f"read  {len(cases)} takes with one word swapped")

    print(f"\nthreshold {_OVERLAP_MIN}, floor {_MIN_PHONES}")
    print(f"\n{'ref cut':<8}{'compare':<12}{'judged':>7}"
          f"{'caught wrong':>16}{'kept right':>15}{'loss/lost':>11}")
    summary, rows = {}, []
    for cut_name in ("flat", "tile"):
        for how in ("anywhere", "ordered", "partition", "slot_direct"):
            caught = {"n": 0, "hit": 0}
            kept = {"n": 0, "hit": 0}
            judged = sum(
                1 for sent in SWAPS for _w, u in refs[sent][cut_name]
                if len(u) >= _MIN_PHONES
            )
            loss_lost = None
            for c in cases:
                pairs = refs[c["sentence"]][cut_name]
                if how in ("ordered", "partition"):
                    given = hand_out([u for _w, u in pairs], c["whole"])
                else:
                    given = [None] * len(pairs)
                for idx, (word, ref_u) in enumerate(pairs):
                    if len(ref_u) < _MIN_PHONES:
                        continue
                    is_target = word.lower() == c["target"].lower()
                    if how == "anywhere":
                        ratio = best_window_overlap(ref_u, c["whole"])
                    elif how == "ordered":
                        seg = given[idx]
                        ratio = best_window_overlap(ref_u, seg) if seg else 0.0
                    elif how == "partition":
                        seg = given[idx]
                        ratio = overlap_ratio(ref_u, seg) if seg else 0.0
                    else:
                        want = c["wrong"] if is_target else word
                        seg = c["slots"].get(want) or c["slots"].get(word) or []
                        ratio = overlap_ratio(ref_u, seg) if seg else 0.0
                    if is_target:
                        caught["n"] += 1
                        caught["hit"] += ratio < _OVERLAP_MIN
                        if c["target"] == "loss":
                            loss_lost = ratio
                    else:
                        kept["n"] += 1
                        kept["hit"] += ratio >= _OVERLAP_MIN
                    rows.append({
                        "cut": cut_name, "how": how, "slot": word,
                        "swapped": c["target"], "wrong": c["wrong"],
                        "ref_units": len(ref_u), "ratio": round(ratio, 3),
                        "is_target": is_target,
                    })
            cr = caught["hit"] / caught["n"] if caught["n"] else 0.0
            kr = kept["hit"] / kept["n"] if kept["n"] else 0.0
            ll = f"{loss_lost:.2f}" if loss_lost is not None else "-"
            print(f"{cut_name:<8}{how:<12}{judged:>7}"
                  f"{caught['hit']:>9}/{caught['n']:<3}{cr:>5.0%}"
                  f"{kept['hit']:>9}/{kept['n']:<4}{kr:>5.0%}{ll:>11}")
            summary[f"{cut_name}|{how}"] = {
                "judged": judged, "caught": f"{caught['hit']}/{caught['n']}",
                "caught_rate": round(cr, 3), "kept": f"{kept['hit']}/{kept['n']}",
                "kept_rate": round(kr, 3), "loss_lost": loss_lost,
            }

    pathlib.Path(".cache/halfgap_report.json").write_text(
        json.dumps({"summary": summary, "rows": rows, "refs": refs},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print("\nwrote .cache/halfgap_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
