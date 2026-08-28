#!/usr/bin/env python3
"""
무엇을: Cloud Run `/api/status` 가 기대 버전·figure 파이프라인 게이트를 만족하는지 확인.
왜: 배포 직후 회귀 — Azure 키 누락 CD·PyMuPDF fallback 재발 방지 (design/25·32·154).
다음에: GitHub CD 성공 후 Actions 스텝으로 호출.
"""

from __future__ import annotations

import argparse
import json
import re
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


def _rich_v_num(label: str) -> int | None:
    m = re.match(r"^rich-v(\d+)$", (label or "").strip().lower())
    return int(m.group(1)) if m else None


def check_status(
    data: dict[str, Any],
    *,
    expect_version: str | None = None,
    require_azure_layout: bool = False,
    min_pipeline: str | None = None,
) -> list[str]:
    """실패 이유 목록 (비어 있으면 합격). edge: 빈/이상 JSON 필드."""
    errs: list[str] = []
    if data.get("ok") is not True:
        errs.append("ok_not_true")
    ver = str(data.get("version") or "")
    if expect_version and ver != expect_version:
        errs.append(f"version_got_{ver}_want_{expect_version}")
    if require_azure_layout:
        if data.get("azure_layout") is not True:
            errs.append("azure_layout_false")
        if data.get("azure_layout_enabled") is not True:
            errs.append("azure_layout_disabled")
    if min_pipeline:
        live = str(data.get("pipeline_version") or "")
        want_n = _rich_v_num(min_pipeline)
        live_n = _rich_v_num(live)
        if want_n is None:
            errs.append(f"min_pipeline_invalid_{min_pipeline}")
        elif live_n is None:
            errs.append(f"pipeline_version_unrecognized_{live}")
        elif live_n < want_n:
            errs.append(f"pipeline_got_{live}_want_min_{min_pipeline}")
    return errs


def read_repo_app_version() -> str:
    """app.py version string — CD --expect 기본값."""
    app_py = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "src"
        / "sentence_reading"
        / "api"
        / "app.py"
    )
    text = app_py.read_text(encoding="utf-8")
    m = re.search(r'"version":\s*"([^"]+)"', text)
    return m.group(1) if m else ""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Verify ASR Cloud Run /api/status")
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument(
        "--expect",
        default="",
        help="expected app version (default: read from app.py)",
    )
    p.add_argument(
        "--require-azure-layout",
        action="store_true",
        help="fail if azure_layout or azure_layout_enabled is false",
    )
    p.add_argument(
        "--min-pipeline",
        default="",
        help="minimum PIPELINE_VERSION e.g. rich-v20 (design/151 slot carousel)",
    )
    p.add_argument("--timeout", type=float, default=60.0)
    args = p.parse_args(argv)
    expect = str(args.expect or "").strip() or read_repo_app_version()
    min_pipe = str(args.min_pipeline or "").strip() or None
    try:
        data = fetch_status(args.url, timeout=float(args.timeout))
    except (ValueError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        print(f"FAIL fetch: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    errs = check_status(
        data,
        expect_version=expect or None,
        require_azure_layout=bool(args.require_azure_layout),
        min_pipeline=min_pipe,
    )
    print(
        json.dumps(
            {
                "ok": not errs,
                "version": data.get("version"),
                "reading_order": data.get("reading_order"),
                "github_cd": data.get("github_cd"),
                "pipeline_version": data.get("pipeline_version"),
                "azure_layout": data.get("azure_layout"),
                "azure_layout_enabled": data.get("azure_layout_enabled"),
                "errors": errs,
            },
            ensure_ascii=False,
        )
    )
    return 0 if not errs else 1


if __name__ == "__main__":
    raise SystemExit(main())
