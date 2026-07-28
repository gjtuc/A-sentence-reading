#!/usr/bin/env python3
"""
무엇을: Cloud Run `/api/status` 가 기대 버전인지 확인.
왜: 배포 직후 회귀 — Windows curl schannel 이슈 회피 (design/25·32).
다음에: GitHub CD 성공 후 Actions 스텝으로 호출.
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import urllib.error
import urllib.request
from typing import Any


DEFAULT_URL = (
    "https://asr-sentence-reading-984608876300.asia-northeast3.run.app/api/status"
)


def fetch_status(url: str, *, timeout: float = 60.0) -> dict[str, Any]:
    """HTTPS status JSON. 인증서 검사 실패 환경에서도 조회 가능."""
    if not url or not str(url).strip():
        raise ValueError("empty_url")
    u = str(url).strip()
    if not u.startswith("https://"):
        raise ValueError("url_must_be_https")
    ctx = ssl._create_unverified_context()
    req = urllib.request.Request(u, method="GET")
    with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("status_not_object")
    return data


def check_status(
    data: dict[str, Any],
    *,
    expect_version: str | None = None,
) -> list[str]:
    """실패 이유 목록 (비어 있으면 합격). edge: 빈/이상 JSON 필드."""
    errs: list[str] = []
    if data.get("ok") is not True:
        errs.append("ok_not_true")
    ver = str(data.get("version") or "")
    if expect_version and ver != expect_version:
        errs.append(f"version_got_{ver}_want_{expect_version}")
    return errs


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Verify ASR Cloud Run /api/status")
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--expect", default="0.2.36", help="expected version string")
    p.add_argument("--timeout", type=float, default=60.0)
    args = p.parse_args(argv)
    try:
        data = fetch_status(args.url, timeout=float(args.timeout))
    except (ValueError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        print(f"FAIL fetch: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    errs = check_status(data, expect_version=str(args.expect or "") or None)
    print(
        json.dumps(
            {
                "ok": not errs,
                "version": data.get("version"),
                "reading_order": data.get("reading_order"),
                "github_cd": data.get("github_cd"),
                "pipeline_version": data.get("pipeline_version"),
                "errors": errs,
            },
            ensure_ascii=False,
        )
    )
    return 0 if not errs else 1


if __name__ == "__main__":
    raise SystemExit(main())
