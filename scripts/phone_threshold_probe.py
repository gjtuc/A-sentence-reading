"""design/366 - is 0.72 the right sound-overlap threshold?

Reads recorded `practice_skill_scored` rows and measures the overlap ratio the
sound fallback actually sees, using the same functions the scorer uses.

Labels come from the data, not from a human pass:

* positive - the lexical compare already matched the slot, so the speaker
  demonstrably said that word. Whatever ratio these produce is the ratio a
  correct read looks like.
* negative - the slot's target is paired with the heard stream of a *different*
  take, which the speaker was not reading. Whatever ratio these produce is the
  ratio a wrong word looks like.

The threshold has to sit above the negatives and below as many positives as
possible. Prints counts only; IPA goes to the detail file (cp949 consoles die on
it).

    python scripts/phone_threshold_probe.py --rows data/scored.jsonl
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from sentence_reading.llm.phone_match import (  # noqa: E402
    _MIN_PHONES,
    _OVERLAP_MIN,
    best_window_overlap,
    overlap_ratio,
    split_phone_units,
)

SWEEP = [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.72, 0.75, 0.80, 0.85]


class Slot:
    """One printed word: its dictionary phones and whether the words matched."""

    __slots__ = ("piece", "target", "lexical", "take")

    def __init__(self, piece: str, target: str, lexical: bool, take: int) -> None:
        self.piece = piece
        self.target = target
        self.lexical = lexical
        self.take = take


def slice_heard(targets: list[str], heard: str) -> list[str]:
    """Same proportional cut as `_sliceHeardPhones` in skill_score.dart.

    The waveform model returns one flat stream for the whole take. Each slot
    claims as many sounds as its dictionary reading has.
    """
    flat = split_phone_units(heard)
    if len(flat) < 2:
        return [heard] if heard.strip() else []
    out: list[str] = []
    index = 0
    for target in targets:
        count = len(split_phone_units(target))
        if count <= 0 or index >= len(flat):
            out.append("")
            continue
        end = min(index + count, len(flat))
        out.append(" ".join(flat[index:end]))
        index = end
    return out


def best_ratio(target: str, slices: list[str]) -> float:
    """Highest overlap against any slice, which is what `phones_close` scans."""
    left = split_phone_units(target)
    if len(left) < _MIN_PHONES:
        return -1.0
    best = 0.0
    for piece in slices:
        right = split_phone_units(piece)
        if not right:
            continue
        got = overlap_ratio(left, right)
        if got > best:
            best = got
    return best


def window_ratio(target: str, flat: list[str]) -> float:
    """What ships now: walk the whole heard stream (`best_window_overlap`).

    The fixed slice assumed eSpeak and the waveform model emit the same number of
    sounds per word. They do not, so the cut drifted further out of step with
    every word and a late slot was compared against a window of the right length
    in the wrong place.
    """
    left = split_phone_units(target)
    if len(left) < _MIN_PHONES:
        return -1.0
    return best_window_overlap(left, flat)


def load(path: pathlib.Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        d = row.get("details") or {}
        hits = d.get("slot_hits") or ""
        targets = [t.strip() for t in (d.get("target_phones") or "").split(" | ")]
        pieces = [p.strip() for p in (d.get("slot_pieces") or "").split(" | ")]
        heard = d.get("heard_phones") or ""
        if not hits or not heard or len(targets) != len(hits):
            continue
        rows.append({"hits": hits, "targets": targets, "pieces": pieces, "heard": heard})
    return rows


def buckets(values: list[float]) -> str:
    """Ten-percent bins, so the two distributions can be read side by side."""
    if not values:
        return "(none)"
    edges = [i / 10 for i in range(11)]
    counts = [0] * 10
    for v in values:
        idx = min(int(v * 10), 9)
        counts[idx] += 1
    total = len(values)
    return " ".join(
        f"{int(edges[i] * 100):>3}:{counts[i] * 100 // total:>2}%" for i in range(10)
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", required=True, help="pull_evidence jsonl of practice_skill_scored")
    ap.add_argument("--detail", default="data/phone_threshold_detail.txt")
    ap.add_argument("--pairs", type=int, default=6, help="cross-take negatives per slot")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument(
        "--mode",
        choices=("slice", "window", "both"),
        default="both",
        help="slice = what ships today; window = walk the whole heard stream",
    )
    args = ap.parse_args()

    rows = load(pathlib.Path(args.rows))
    if not rows:
        print(json.dumps({"ok": False, "error": "no_usable_rows"}))
        return 1

    slots: list[Slot] = []
    take_slices: list[list[str]] = []
    take_flat: list[list[str]] = []
    for take, row in enumerate(rows):
        pieces = row["pieces"]
        take_slices.append(slice_heard(row["targets"], row["heard"]))
        take_flat.append(split_phone_units(row["heard"]))
        for i, target in enumerate(row["targets"]):
            slots.append(
                Slot(
                    piece=pieces[i] if i < len(pieces) else "?",
                    target=target,
                    lexical=row["hits"][i] == "1",
                    take=take,
                )
            )

    modes = ("slice", "window") if args.mode == "both" else (args.mode,)
    miss: list[tuple[float, str]] = []
    print(f"rows={len(rows)} slots={len(slots)}")
    for mode in modes:

        def score(slot: Slot, take: int) -> float:
            if mode == "slice":
                return best_ratio(slot.target, take_slices[take])
            return window_ratio(slot.target, take_flat[take])

        rng = random.Random(args.seed)
        pos: list[float] = []
        neg: list[float] = []
        short_pos = 0
        for slot in slots:
            own = score(slot, slot.take)
            if slot.lexical:
                if own < 0:
                    short_pos += 1
                else:
                    pos.append(own)
            elif own >= 0 and mode == modes[-1]:
                miss.append((own, slot.piece))
            # The same target against takes the speaker was not reading.
            for _ in range(args.pairs):
                other = rng.randrange(len(take_slices))
                if other == slot.take:
                    continue
                got = score(slot, other)
                if got >= 0:
                    neg.append(got)

        print()
        print(f"=== mode={mode}")
        print(f"positives={len(pos)} (too short to ever pass: {short_pos})")
        print(f"negatives={len(neg)} cross-take pairings")
        print("ratio distribution, percent of each group per 10% bin")
        print(f"  positive  {buckets(pos)}")
        print(f"  negative  {buckets(neg)}")
        print(f"{'thresh':>7} {'pos kept':>9} {'neg leak':>9}   verdict")
        for t in SWEEP:
            keep = sum(1 for v in pos if v >= t) / len(pos) if pos else 0.0
            leak = sum(1 for v in neg if v >= t) / len(neg) if neg else 0.0
            mark = "  <- live" if abs(t - _OVERLAP_MIN) < 1e-9 and mode == "slice" else ""
            print(f"{t:>7.2f} {keep:>8.1%} {leak:>8.1%}{mark}")

    detail = pathlib.Path(args.detail)
    detail.parent.mkdir(parents=True, exist_ok=True)
    miss.sort(reverse=True)
    with detail.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("# slots the words missed, by how close the sound came\n")
        for ratio, piece in miss[:400]:
            fh.write(f"{ratio:.3f}\t{piece}\n")
    print()
    print(f"words-missed slots: {len(miss)}, detail -> {detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
