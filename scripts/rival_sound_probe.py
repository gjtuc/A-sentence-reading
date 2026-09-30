"""At the frames a reference sound landed on, what else did the model hear?

The certainty score asks one question: how sure was the model about the sound
the reference asked for. It never asks what the model would have said if left
alone. Those are different questions, and the gap between them is the standard
weakness of this kind of score: lining a fixed sequence up against frames is a
search, and a search can find the frames that flatter the target.

So for the words no score catches - `grew` read as `grow`, `fed` read as `fat` -
this prints, at exactly the frames the alignment gave each reference sound, the
three sounds the model ranked highest. If the reference sound is the winner
there, the model genuinely heard it and no rearranging of the score will help.
If it is a runner-up, the alignment flattered it and the score has a hole.

    python scripts/rival_sound_probe.py
"""

from __future__ import annotations

import json
import pathlib
import sys
import unicodedata

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import importlib  # noqa: E402

from ctc_prob_score_probe import logprobs  # noqa: E402
from human_label_probe import norm, safe, said_set  # noqa: E402

wide = importlib.import_module("timing_spread_probe")

TAKES = pathlib.Path(".cache/takes")
REFS = pathlib.Path(".cache/human_refs_tokens.json")
SCORED = pathlib.Path(".cache/human_takes.json")
OUT = pathlib.Path(".cache/rival_sound.json")
LOOK = 6


def nm(sym: str) -> str:
    return "-".join(
        unicodedata.name(c, "U%04X" % ord(c)).split()[-1] for c in sym
    )


def pick(rows: list[dict], cards: dict) -> list[dict]:
    """Words the transcript says went wrong that every score let through."""
    good = [r for r in rows if not r["bad"]]
    bad = [r for r in rows if r["bad"]]

    def line90(values):
        ranked = sorted(values)
        at = int(round(0.10 * (len(ranked) - 1)))
        return ranked[max(0, min(at, len(ranked) - 1))]

    lw = line90([x["worst"] for x in good])
    lf = line90([x["full"] for x in good])
    ls = line90([x["sure"] for x in good])
    out = [
        x for x in bad
        if x["worst"] >= lw and x["full"] >= lf and x["sure"] >= ls
        and x["word"][:1].isalpha() and x["n"] >= 3
    ]
    out.sort(key=lambda x: -x["sure"])
    return out


def main() -> int:
    rows = json.loads(SCORED.read_text(encoding="utf-8"))
    refs = json.loads(REFS.read_text(encoding="utf-8"))
    cards = {}
    for path in TAKES.glob("*.json"):
        one = json.loads(path.read_text(encoding="utf-8"))
        cards[one["stem"]] = one
    for row in rows:
        row["bad"] = (
            0 if norm(row["word"]) in said_set(cards[row["stem"]].get("heard") or "")
            else 1
        )

    chosen = pick(rows, cards)
    print(f"{len(chosen)} real words that no score caught; showing {LOOK}")
    m = wide.M()
    report = []

    import torchaudio.functional as F
    from sentence_reading.llm.hear_waveform import _pcm16k

    ids = {s: i for i, s in m.inv.items()}
    seen: set[str] = set()
    for row in chosen:
        key = norm(row["word"])
        if key in seen:
            continue
        seen.add(key)
        card = cards[row["stem"]]
        sent = (card.get("expected") or "").strip()
        ref = refs.get(sent) or []
        if not ref:
            continue
        where = [i for i, (w, _s) in enumerate(ref) if w == row["word"]]
        if not where:
            continue
        which = where[0]

        pcm = _pcm16k((TAKES / f"{row['stem']}.m4a").read_bytes())
        sheet = logprobs(m, pcm, 16000)
        flat, owner = [], []
        for i, (_w, syms) in enumerate(ref):
            for s in syms:
                if s in ids:
                    flat.append(ids[s])
                    owner.append(i)
        if not flat or len(flat) >= sheet.shape[0]:
            continue
        targets = m.torch.tensor([flat], dtype=m.torch.int32)
        aligned, score = F.forced_align(sheet.unsqueeze(0), targets, blank=m.pad)
        spans = F.merge_tokens(aligned[0], score[0].exp(), blank=m.pad)
        if len(spans) != len(flat):
            continue

        print()
        print("=" * 66)
        print(f"{safe(row['word'])}   sounds {row['n']}"
              f"   worst {row['worst']:.3f}   average {row['sure']:.3f}")
        print(f"  screen : {safe(sent)[:62]}")
        print(f"  wrote  : {safe((card.get('heard') or '').strip())[:62]}")
        print("  each reference sound, and the three loudest sounds there:")
        lines = []
        prob = sheet.exp()
        for k, span in enumerate(spans):
            if owner[k] != which:
                continue
            here = prob[int(span.start):int(span.end)].mean(dim=0)
            top = m.torch.topk(here, 4)
            rivals = []
            for value, index in zip(top.values.tolist(), top.indices.tolist()):
                name = "blank" if index == m.pad else nm(m.inv[index])
                rivals.append((name, round(value, 3)))
            want = nm(m.inv[flat[k]])
            beaten = rivals[0][0] not in ("blank", want)
            print(f"    {want:<14} {float(span.score):.3f}"
                  f"   loudest: "
                  + ", ".join(f"{n} {v:.2f}" for n, v in rivals[:3])
                  + ("   <- beaten" if beaten else ""))
            lines.append({"want": want, "score": float(span.score),
                          "rivals": rivals, "beaten": beaten})
        report.append({
            "word": row["word"], "sent": sent,
            "heard": (card.get("heard") or "").strip(),
            "worst": row["worst"], "sure": row["sure"], "sounds": lines,
        })
        if len(report) >= LOOK:
            break

    beaten = sum(1 for r in report for s in r["sounds"] if s["beaten"])
    total = sum(len(r["sounds"]) for r in report)
    print()
    print(f"reference sounds that another sound beat at their own frames:"
          f" {beaten}/{total}")
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
