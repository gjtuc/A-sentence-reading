#!/usr/bin/env python3
"""design/371 - read live evidence and say whether sound scoring is working.

The evidence stream already carries every number this needs, but nothing read it,
so a scorer that had been dead for three releases still looked fine from here.
This turns the rows into the four answers that matter and exits non-zero when one
of them is bad, so a person does not have to eyeball JSONL to notice.

    python scripts/sound_score_verdict.py --since 2h

Exit 0 verdict ok, 1 a fault worth fixing, 2 nobody has read anything yet.

Phone strings are never printed. They hold IPA, and this console is cp949.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent

# A reference is built in the background, so the first ask for a sentence gets
# nothing back on purpose. Only these two mean "wait one reading".
REF_PENDING = {"queued", "building"}
REF_GOOD = {"ready"}

# Codes that mean the take produced no usable per-word verdict. `sound_too_short`
# is honest rather than broken, but if every take says it, the reference builder
# is handing out two-sound words and that is a fault.
NOT_SCORED = {"sound_ref_missing", "sound_too_short", "no_spans", "walk_past_end"}

# Judged slots below which passing nothing is just one short hurried take.
NOTHING_PASSED_MIN = 5

# Under this many refusals the split between near and clear ones is noise, and a
# single hurried take would raise it.
NEAR_MIN = 10


def _ascii(text: object) -> str:
    return str(text).encode("ascii", "replace").decode("ascii")


def _pull(since: str, limit: int) -> list[dict]:
    """Ask GCS for the rows. A temp file, because stdout capture fights cp949."""
    with tempfile.TemporaryDirectory() as tmp:
        out = pathlib.Path(tmp) / "ev.jsonl"
        proc = subprocess.run(
            [
                sys.executable,
                str(HERE / "pull_evidence.py"),
                "--since",
                since,
                "--limit",
                str(limit),
                "--out",
                str(out),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if not out.exists():
            print("pull_evidence failed:", _ascii(proc.stderr)[:400])
            return []
        return _load(out)


def _load(path: pathlib.Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rows.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return rows


def _words_off_the_sheet(rows: list[dict]) -> tuple[collections.Counter, int, int]:
    """Which printed words the scorer could not put a question about, and how many.

    `slot_hits` marks one character per printed word and design/371 writes `-`
    where the reference was too short to tell words apart. Lining it up with
    `slot_pieces` names them, which is the only way to see that `the` and `a`
    stopped being marked wrong.
    """
    off: collections.Counter = collections.Counter()
    off_n = 0
    slot_n = 0
    for row in rows:
        det = row.get("details") or {}
        hits = str(det.get("slot_hits") or "")
        pieces = str(det.get("slot_pieces") or "").split(" | ")
        slot_n += len(hits)
        for i, mark in enumerate(hits):
            if mark != "-":
                continue
            off_n += 1
            # A truncated slot_pieces loses the tail names but not the count.
            word = pieces[i].strip() if i < len(pieces) else ""
            off[word or "?"] += 1
    return off, off_n, slot_n


def _near_misses(rows: list[dict]) -> tuple[list[int], int]:
    """How far under the line each refused word sat, over every scored take.

    design/377 - a sheet of marks cannot tell a word refused by a hair from one
    refused by a mile, and the two want opposite fixes: the first says the line is
    in the wrong place, the second says the reading was wrong. `slot_scores`
    carries the distance, so the question is answerable from the log.

    Returns the shortfalls in hundredths and how many words were asked about.
    """
    short: list[int] = []
    asked = 0
    for row in rows:
        det = row.get("details") or {}
        scores = str(det.get("slot_scores") or "").split()
        try:
            line = int(det.get("line_used") or 0) / 10
        except (TypeError, ValueError):
            continue
        if not scores or line <= 0:
            continue
        for field in scores:
            if field == "-":
                continue
            try:
                got = int(field)
            except ValueError:
                continue
            asked += 1
            if got < line:
                short.append(round(line - got))
    return short, asked


def _stale_rows(rows: list[dict]) -> tuple[int, int]:
    """Cached sentences holding sounds design/373 says cannot be scored against.

    Split by what the phone did with them: kept and compared against, or asked
    for again. A build older than the one that writes `stale_span_n` reports
    neither, which is why a clean window is not proof on its own.
    """
    kept = retried = 0
    for row in rows:
        if row.get("kind") != "practice_skill_spoken":
            continue
        det = row.get("details") or {}
        try:
            n = int(det.get("stale_span_n") or 0)
        except (TypeError, ValueError):
            continue
        if n <= 0:
            continue
        if str(row.get("code")) == "cache_hit":
            kept += 1
        else:
            retried += 1
    return kept, retried


def main() -> int:
    ap = argparse.ArgumentParser(description="design/371 sound scoring verdict")
    ap.add_argument("--since", default="2h", help="e.g. 30m, 2h, 1d")
    ap.add_argument("--jsonl", help="read a file instead of pulling live")
    ap.add_argument("--limit", type=int, default=200000)
    ap.add_argument(
        "--expect-version",
        default="",
        help="only count client rows from this app_version",
    )
    args = ap.parse_args()

    rows = _load(pathlib.Path(args.jsonl)) if args.jsonl else _pull(args.since, args.limit)

    server = [
        r
        for r in rows
        if r.get("kind") == "practice_skill_align"
        and (r.get("details") or {}).get("phase") == "server_align"
    ]
    client = [
        r
        for r in rows
        if r.get("kind") == "practice_skill_align"
        and (r.get("details") or {}).get("phase") == "align"
    ]
    if args.expect_version:
        client = [r for r in client if r.get("app_version") == args.expect_version]
        server = [r for r in server if r.get("app_version") in ("", args.expect_version, None)]

    faults: list[str] = []

    print("== reference build (server)")
    if not server:
        print("  no sentence was asked for in this window")
    else:
        # A row from before 0.3.405 has no such key at all. Calling that a broken
        # builder would make every old window look like a fault.
        fresh = [r for r in server if "sound_ref_code" in (r.get("details") or {})]
        stale = len(server) - len(fresh)
        if stale:
            print(f"  {stale:5d}  (rows older than 0.3.405, no such field)")
        codes = collections.Counter(
            str((r.get("details") or {}).get("sound_ref_code") or "none") for r in fresh
        )
        for code, n in codes.most_common():
            print(f"  {n:5d}  {_ascii(code)}")
        if not fresh:
            print("  nothing to judge here: every row predates the field")
        else:
            last = (fresh[-1].get("details") or {})
            print(
                "  counters: ok={} bad={} waiting={} run={} fail={} status={}".format(
                    last.get("sound_ref_ok"),
                    last.get("sound_ref_bad"),
                    last.get("sound_ref_waiting"),
                    last.get("sound_ref_run"),
                    _ascii(last.get("sound_ref_fail")),
                    last.get("sound_ref_status"),
                )
            )
            fail = str(last.get("sound_ref_fail") or "none")
            if fail not in ("none", "None", ""):
                faults.append(
                    "ref_build_failing:{}:{}".format(_ascii(fail), last.get("sound_ref_status"))
                )
            if int(last.get("sound_ref_run") or 0) >= 5:
                faults.append("ref_build_sunk")
            if not (set(codes) & REF_GOOD):
                pending = set(codes) & REF_PENDING
                faults.append("ref_only_pending" if pending else "ref_never_ready")

    print("== scoring (phone)")
    if not client:
        print("  nobody read a sentence in this window")
    else:
        codes = collections.Counter(
            str((r.get("details") or {}).get("slot_code") or "none") for r in client
        )
        for code, n in codes.most_common():
            print(f"  {n:5d}  {_ascii(code)}")
        scored = [r for r in client if str((r.get("details") or {}).get("slot_code")) not in NOT_SCORED]
        print(f"  takes {len(client)}   with a per-word verdict {len(scored)}")
        if not scored:
            faults.append("nothing_scored")
        off, off_n, slot_n = _words_off_the_sheet(client)
        asked = slot_n - off_n
        sound_pass = sum(int((r.get("details") or {}).get("sound_pass_n") or 0) for r in scored)
        print(f"  slots the sound compare passed: {sound_pass} of {asked} asked")
        # design/373 - not one word passing is what a broken compare looks like,
        # and it is the one result reading badly cannot produce: a misread word
        # still shares sounds with the printed one somewhere. Under five slots a
        # single hurried take could do it, so the count decides, not the share.
        if asked >= NOTHING_PASSED_MIN and not sound_pass:
            faults.append(f"nothing_passed:{asked}")

        share = (100.0 * off_n / slot_n) if slot_n else 0.0
        print("== words the scorer could not ask about (left the sheet)")
        print(f"  {off_n} of {slot_n} slots ({share:.1f}%)")
        for word, n in off.most_common(12):
            print(f"  {n:5d}  {_ascii(word)}")

        print("== account pass line")
        withline = [r for r in client if "line_n" in (r.get("details") or {})]
        if not withline:
            print("  no row carried a line; this build is older than 0.3.406")
            # Only a fault when a version was named. Otherwise the window simply
            # reaches back past the release and that is not a defect.
            if args.expect_version:
                faults.append("no_pass_line_field")
        else:
            last = withline[-1].get("details") or {}
            n = int(last.get("line_n") or 0)
            print(
                "  n={} avg={:.3f} used={:.3f} ({})".format(
                    n,
                    (last.get("line_avg") or 0) / 1000.0,
                    (last.get("line_used") or 0) / 1000.0,
                    "own line" if n >= 40 else "still the fixed line",
                )
            )

    short, asked_n = _near_misses(client)
    if asked_n:
        print("== how close the refused words came")
        hair = sum(1 for s in short if s <= 5)
        close = sum(1 for s in short if 5 < s <= 15)
        far = sum(1 for s in short if s > 15)
        print(f"  refused {len(short)} of {asked_n} asked")
        print(f"    within 0.05 of the line: {hair}")
        print(f"    0.05 to 0.15 under:      {close}")
        print(f"    more than 0.15 under:    {far}")
        # A line sitting inside the spread of ordinary reading turns small
        # differences into failures, and that shows up as most refusals being
        # near ones rather than clear ones.
        if len(short) >= NEAR_MIN and hair + close > far:
            faults.append(f"line_inside_spread:{hair + close}_of_{len(short)}")
    elif client:
        print("== how close the refused words came")
        print("  no build in this window recorded it (older than 0.3.417)")

    print("== reference sounds by a reader we do not score against")
    kept, retried = _stale_rows(rows)
    if not kept and not retried:
        print("  none")
    else:
        print(f"  rows kept and scored against: {kept}   rows asked again: {retried}")
    # A row the phone kept is a row it scored against, so every word of that
    # sentence fails however it is read. Asking again is the fix working.
    if kept:
        faults.append(f"stale_ref_kept:{kept}")

    print("== verdict")
    if not server and not client:
        print("  no_traffic - open a paper on the phone and read a few sentences")
        return 2
    if faults:
        for f in faults:
            print("  FAULT", _ascii(f))
        return 1
    print("  ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
