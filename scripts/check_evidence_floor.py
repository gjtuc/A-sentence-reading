#!/usr/bin/env python3
"""Fail if frozen 169c/d/e evidence sensors were removed (design/169g)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sentence_reading.llm.evidence_floor import (  # noqa: E402
    EVIDENCE_FLOOR_VERSION,
    verify_evidence_floor,
)


def main() -> int:
    if os.environ.get("ASR_SKIP_EVIDENCE_FLOOR", "").strip() in ("1", "true", "yes"):
        print(
            json.dumps(
                {"ok": True, "skipped": True, "floor_version": EVIDENCE_FLOOR_VERSION},
                ensure_ascii=False,
            )
        )
        return 0
    errs = verify_evidence_floor(root=ROOT)
    payload = {
        "ok": not errs,
        "floor_version": EVIDENCE_FLOOR_VERSION,
        "errors": errs,
    }
    print(json.dumps(payload, ensure_ascii=False))
    if errs:
        print(
            "EVIDENCE FLOOR BLOCKED — do not remove 169c/d/e sensors "
            "(design/169g). Emergency: ASR_SKIP_EVIDENCE_FLOOR=1",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
