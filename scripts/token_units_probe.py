"""design/374 - is a sound one token or one letter?

The reference and the take both come out of the same waveform model, whose
alphabet is 392 tokens. Several of those tokens are two or three letters long:
`eI`, `oU`, `aI`, `@l`, `tS`, `dZ`, and the r-coloured vowels. `split_phone_units`
cuts on letters, so it tears those in half and counts one sound as two.

On the 128 reference sentences that is 45% of words counted longer than they are
and 10% more units overall. A torn token can only match if the other side tears
at the same place, so the tear is a one-sided penalty against the speaker.

This measures the two rules on the same recordings:

* `char`  - today's rule, `split_phone_units` over the joined string
* `token` - the model's own tokens, compared as they come

Heard token runs are cached per take, so only the first run pays for the model.

    python scripts/token_units_probe.py
    python scripts/token_units_probe.py --fresh

Decoding the takes needs fmpeg on PATH, the same binary the server shells out
to. Without it every take raises FileNotFoundError and the report reads as zero
words rather than as a missing tool. There is one bundled with imageio_ffmpeg:

    python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"

Copy it somewhere on PATH named fmpeg.exe.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import statistics as stat
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from sentence_reading.llm.phone_match import (  # noqa: E402
    best_window_overlap,
    split_phone_units,
)

REFS = pathlib.Path(".cache/human_refs_tokens.json")
HEARD = pathlib.Path(".cache/human_heard_tokens.json")
OUT = pathlib.Path(".cache/token_units.json")
LINE = 0.72
MIN_UNITS = 3


def _ascii(text: object) -> str:
    return str(text).encode("ascii", "replace").decode()


def load_heard(fresh: bool) -> dict[str, list[str]]:
    if fresh or not HEARD.is_file():
        return {}
    try:
        return json.loads(HEARD.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def fill_heard(cards: list[dict], got: dict[str, list[str]]) -> dict[str, list[str]]:
    """Run the model on the takes we have not heard yet, and remember them."""
    import importlib

    from sentence_reading.llm.hear_waveform import _pcm16k

    want = [c for c in cards if c["stem"] not in got]
    if not want:
        print(f"every take already heard ({len(got)} cached)")
        return got
    print(f"{len(want)} takes to hear, {len(got)} already cached")
    wide = importlib.import_module("timing_spread_probe")
    m = wide.M()
    takes = pathlib.Path(".cache/takes")
    clock = time.monotonic()
    for n, card in enumerate(want, 1):
        stem = card["stem"]
        try:
            pcm = _pcm16k((takes / f"{stem}.m4a").read_bytes())
            got[stem] = [s["sym"] for s in m.run(pcm, 16000)]
        except Exception as exc:  # noqa: BLE001
            print(f"  skip ({type(exc).__name__}) {_ascii(stem)[:24]}")
            got[stem] = []
        if n % 25 == 0 or n == len(want):
            HEARD.write_text(json.dumps(got, ensure_ascii=False), encoding="utf-8")
            gone = time.monotonic() - clock
            print(f"  heard {n}/{len(want)}, {gone / n:.2f}s per take")
    HEARD.write_text(json.dumps(got, ensure_ascii=False), encoding="utf-8")
    return got


def sidecars() -> list[dict]:
    """Takes that recorded the sentence on screen, so a word can be looked up."""
    out = []
    for p in sorted(pathlib.Path(".cache/takes").glob("*.json")):
        try:
            card = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not str(card.get("expected") or "").strip():
            continue
        card["stem"] = p.stem
        out.append(card)
    return out


def bare(word: str) -> str:
    return "".join(c for c in word.lower() if c.isalnum())


def score(rule: str, raws: list[str], run: list[str]) -> tuple[float, int]:
    """Overlap of one printed word against the whole take, and the unit count."""
    if rule == "token":
        left, flat = list(raws), list(run)
    else:
        left = split_phone_units(" ".join(raws))
        flat = split_phone_units(" ".join(run))
    if len(left) < MIN_UNITS:
        return -1.0, len(left)
    return best_window_overlap(left, flat), len(left)


def main() -> int:
    ap = argparse.ArgumentParser(description="design/374 token units vs letters")
    ap.add_argument("--fresh", action="store_true", help="re-hear every take")
    args = ap.parse_args()

    refs = json.loads(REFS.read_text(encoding="utf-8"))
    cards = [c for c in sidecars() if (c.get("expected") or "").strip() in refs]
    print(f"{len(cards)} takes, {len(refs)} distinct sentences")
    heard = fill_heard(cards, load_heard(args.fresh))

    rows: list[dict] = []
    for card in cards:
        run = heard.get(card["stem"]) or []
        if not run:
            continue
        said = {bare(w) for w in (card.get("heard") or "").split()}
        for word, raws in refs[(card["expected"]).strip()]:
            row = {
                "word": word,
                "bad": 0 if bare(word) in said else 1,
                "tier": card.get("skill_tier"),
            }
            for rule in ("char", "token"):
                got, n = score(rule, raws, run)
                row[rule] = got
                row[f"{rule}_n"] = n
            rows.append(row)

    OUT.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    report(rows)
    print(f"\nwrote {OUT}")
    return 0


def report(rows: list[dict]) -> None:
    print(f"\n{len(rows)} printed words over the takes")

    print("\n== words the scorer may ask about (reference of 3 or more)")
    for rule in ("char", "token"):
        askable = [r for r in rows if r[rule] >= 0.0]
        print(f"  {rule:5s} {len(askable):6d} of {len(rows)}"
              f"  ({100.0 * len(askable) / max(1, len(rows)):.1f}%)")

    # Only words both rules can ask about can be compared; the rest differ for a
    # reason the pass line has nothing to do with.
    both = [r for r in rows if r["char"] >= 0.0 and r["token"] >= 0.0]
    good = [r for r in both if not r["bad"]]
    bad = [r for r in both if r["bad"]]
    print(f"\n== both rules can ask: {len(both)} words"
          f"  ({len(good)} the transcript confirms, {len(bad)} it does not)")

    print("\n== overlap, and what the fixed 0.72 line does with it")
    head = f"  {'rule':5s} {'confirmed':>22s} {'not confirmed':>22s}   kept   caught"
    print(head)
    for rule in ("char", "token"):
        gv = [r[rule] for r in good]
        bv = [r[rule] for r in bad]
        kept = sum(1 for v in gv if v >= LINE) / max(1, len(gv))
        caught = sum(1 for v in bv if v < LINE) / max(1, len(bv))
        print(f"  {rule:5s} "
              f"{stat.mean(gv):8.3f} +-{stat.pstdev(gv):6.3f}"
              f"{stat.mean(bv):14.3f} +-{stat.pstdev(bv):6.3f}"
              f"  {100.0 * kept:5.1f}%  {100.0 * caught:5.1f}%")

    # Separation is what the line has to work with, and it does not depend on
    # where the line is put.
    for rule in ("char", "token"):
        gap = stat.mean([r[rule] for r in good]) - stat.mean([r[rule] for r in bad])
        print(f"  {rule:5s} separation {gap:+.3f}")

    print("\n== words the two rules disagree about at 0.72")
    up = [r for r in both if r["char"] < LINE <= r["token"]]
    down = [r for r in both if r["token"] < LINE <= r["char"]]
    print(f"  fail -> pass {len(up):5d}   of which the transcript confirms"
          f" {sum(1 for r in up if not r['bad'])}")
    print(f"  pass -> fail {len(down):5d}   of which the transcript confirms"
          f" {sum(1 for r in down if not r['bad'])}")
    names = collections.Counter(_ascii(r["word"]) for r in up if not r["bad"])
    for word, n in names.most_common(12):
        print(f"    {n:4d}  {word}")


if __name__ == "__main__":
    raise SystemExit(main())
