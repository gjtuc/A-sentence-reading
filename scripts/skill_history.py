"""design/412 - print an account's practice rung history and daily scores.

Reads {prefix}/users/{uid}/practice/skill_v1.json, the copy the phone syncs.
The evidence log keeps seven days; this keeps every rung check since 0.3.450
and every day's score since the store began.

    python scripts/skill_history.py [--uid UID] [--json]

Without --uid the one account that has a skill store is used.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from sentence_reading.llm.gcs_sync import download_bytes, gcs_config, object_name  # noqa: E402
from sentence_reading.llm.practice_gcs import normalize_skill_store  # noqa: E402

KST = dt.timezone(dt.timedelta(hours=9))

REASON_KO = {
    "hold": "그대로",
    "finer": "구간 잘게 (쉽게)",
    "coarser": "구간 크게 (어렵게)",
    "tier_up": "속도 등급 올림",
    "tier_down": "속도 등급 내림",
    "floor": "가장 쉬움이라 그대로",
    "ceiling": "가장 어려움이라 그대로",
    "sample_on": "발음 표본 시작 (고정)",
    "sample_back": "발음 표본 끝, 원래 난이도로",
    "sample_left": "꺼진 표본 정리, 원래 난이도로",
    "reset": "난이도 되돌림",
}


def ladder_n(tier: int, density: int) -> int:
    """mobile skillLadderDisplayN."""
    return tier * 5 + (2 - density) + 1


def find_uid() -> str | None:
    from google.cloud import storage

    cfg = gcs_config()
    users = object_name("users") + "/"
    found = set()
    for blob in storage.Client().list_blobs(cfg.bucket, prefix=users):
        if blob.name.endswith("/practice/skill_v1.json"):
            found.add(blob.name[len(users) :].split("/")[0])
    return found.pop() if len(found) == 1 else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--uid")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    uid = args.uid or find_uid()
    if not uid:
        print("uid_needed: zero or several accounts have a skill store; pass --uid")
        return 2
    raw = download_bytes(object_name("users", uid, "practice", "skill_v1.json"))
    if not raw:
        print("no_skill_store")
        return 1
    store = normalize_skill_store(json.loads(raw.decode("utf-8")))
    if args.json:
        print(json.dumps(store, ensure_ascii=True, indent=1))
        return 0
    out = []
    out.append(
        f"now {ladder_n(store['tier'], store['density'])}/50 "
        f"(tier {store['tier']}, density {store['density']}), ladder_fix {store['ladder_fix']}"
    )
    out.append("")
    out.append("day         takes  avg")
    for day in sorted(store["days"]):
        d = store["days"][day]
        out.append(f"{day}  {d['n']:5d}  {d['sum'] / d['n'] * 100:5.1f}%")
    out.append("")
    out.append("when (KST)        rung      why")
    for r in store["history"]:
        when = dt.datetime.fromtimestamp(r["at"] / 1000, KST).strftime("%Y-%m-%d %H:%M")
        rung = f"{ladder_n(r['t0'], r['d0'])}->{ladder_n(r['t1'], r['d1'])}"
        avg = (
            f"  avg {r['avg'] * 100:.0f}% over {r['n']} blocks, lines {r['lo'] * 100:.0f}/{r['hi'] * 100:.0f}"
            if "avg" in r
            else ""
        )
        out.append(f"{when}  {rung:8s}  {REASON_KO.get(r['why'], r['why'])}{avg}")
    if not store["history"]:
        out.append("(none yet)")
    text = "\n".join(out) + "\n"
    sys.stdout.buffer.write(text.encode(sys.stdout.encoding or "utf-8", errors="replace"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
