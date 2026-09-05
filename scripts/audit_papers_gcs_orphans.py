#!/usr/bin/env python3
"""design/175 Phase A — audit personal papers/ prefixes vs index.json (no deletes).

Usage:
  python scripts/audit_papers_gcs_orphans.py --uid 116191504131668885631
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

_CACHE_ID = re.compile(r"/papers/([a-f0-9]{12})/(.*)$")


def _gsutil() -> str:
    from shutil import which

    for cand in (
        which("gsutil"),
        r"C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gsutil.cmd",
        r"C:\Program Files\Google\Cloud SDK\google-cloud-sdk\bin\gsutil.cmd",
    ):
        if cand and Path(cand).exists():
            return cand
    raise SystemExit("gsutil not found")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--uid", required=True)
    ap.add_argument("--bucket", default="asr-chaheon-warehouse")
    ap.add_argument("--prefix", default="asr")
    ap.add_argument("--json-out", default="")
    args = ap.parse_args()
    gs = _gsutil()
    base = f"gs://{args.bucket}/{args.prefix}/users/{args.uid}/papers"
    index_raw = subprocess.check_output([gs, "cat", f"{base}/index.json"])
    index = json.loads(index_raw.decode("utf-8"))
    indexed = {
        str(e.get("id") or "").strip()
        for e in (index.get("entries") or [])
        if isinstance(e, dict) and e.get("id")
    }
    listing = subprocess.check_output([gs, "ls", "-r", f"{base}/**"], text=True, encoding="utf-8", errors="replace")
    by: dict[str, set[str]] = {}
    for line in listing.splitlines():
        line = line.strip()
        m = _CACHE_ID.search(line)
        if not m:
            continue
        cid, rest = m.group(1), m.group(2).rstrip("/")
        if not rest:
            continue
        top = rest.split("/")[0]
        if top == "figures":
            by.setdefault(cid, set()).add("figures/*")
        else:
            by.setdefault(cid, set()).add(top)

    def kind(names: set[str]) -> str:
        has_s = "session.json" in names
        has_l = "layout_map.json" in names or "slot_plan.json" in names
        has_src = any(x.startswith("source.") for x in names)
        has_f = "figures/*" in names
        if has_s:
            return "full_or_partial_content"
        if not has_s and has_l and not has_f and not has_src:
            return "layout_slot_only"
        if has_f or has_src:
            return "body_without_session"
        return "other"

    rows = []
    for cid, names in sorted(by.items()):
        rows.append(
            {
                "id": cid,
                "in_index": cid in indexed,
                "kind": kind(names),
                "names": sorted(names),
            }
        )
    orphans = [r for r in rows if not r["in_index"]]
    ghosts = sorted(indexed - set(by))
    counts = Counter(r["kind"] for r in orphans)
    report = {
        "uid": args.uid,
        "index_n": len(indexed),
        "prefix_n": len(by),
        "orphan_n": len(orphans),
        "ghost_n": len(ghosts),
        "orphan_kinds": dict(counts),
        "indexed_ids": sorted(indexed),
        "ghost_ids": ghosts,
        "orphans": orphans,
    }
    print(json.dumps({k: report[k] for k in ("uid", "index_n", "prefix_n", "orphan_n", "ghost_n", "orphan_kinds", "indexed_ids")}, ensure_ascii=False, indent=2))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("wrote", args.json_out, file=sys.stderr)
    return 0 if not orphans and not ghosts else 2


if __name__ == "__main__":
    raise SystemExit(main())
