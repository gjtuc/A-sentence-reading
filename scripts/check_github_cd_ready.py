#!/usr/bin/env python3
"""
무엇을: GitHub CD 준비 상태 점검 (시크릿 **값**은 출력하지 않음).
왜: ASR_CD_ENABLED 켜기 전 누락 Secrets/Variables 확인 (design/32).
다음에: gh secret set · 변수 ASR_CD_ENABLED=1.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Any


REQUIRED_SECRETS = (
    "GCP_SA_KEY",
    "ASR_GOOGLE_CLIENT_ID",
    "ASR_AUTH_SECRET",
    "GEMINI_API_KEY",
)
OPTIONAL_SECRETS = (
    "ASR_ADMIN_EMAILS",
    "ASR_KAKAO_REST_API_KEY",
    "ASR_KAKAO_CLIENT_SECRET",
)
REQUIRED_VARS_FOR_ENABLE = ("ASR_CD_ENABLED",)


def _gh_json(args: list[str]) -> Any:
    r = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "gh_failed").strip()[:400])
    return json.loads(r.stdout or "null")


def list_secret_names() -> set[str]:
    data = _gh_json(["secret", "list", "--json", "name"])
    if not isinstance(data, list):
        return set()
    return {str(x.get("name") or "") for x in data if isinstance(x, dict)}


def list_var_map() -> dict[str, str]:
    data = _gh_json(["variable", "list", "--json", "name,value"])
    out: dict[str, str] = {}
    if not isinstance(data, list):
        return out
    for x in data:
        if isinstance(x, dict) and x.get("name"):
            out[str(x["name"])] = str(x.get("value") or "")
    return out


def evaluate(
    *,
    secret_names: set[str],
    variables: dict[str, str],
) -> dict[str, Any]:
    """합격/누락 요약. edge: 빈 이름·부분 카카오."""
    missing_req = [n for n in REQUIRED_SECRETS if n not in secret_names]
    opt_present = {n: (n in secret_names) for n in OPTIONAL_SECRETS}
    kakao_r = opt_present.get("ASR_KAKAO_REST_API_KEY", False)
    kakao_s = opt_present.get("ASR_KAKAO_CLIENT_SECRET", False)
    kakao = "on" if (kakao_r and kakao_s) else ("partial" if (kakao_r or kakao_s) else "off")
    enabled = (variables.get("ASR_CD_ENABLED") or "").strip() == "1"
    ready = not missing_req and kakao != "partial"
    return {
        "ok": ready,
        "cd_enabled": enabled,
        "missing_required_secrets": missing_req,
        "optional_secrets": opt_present,
        "kakao": kakao,
        "can_enable": ready and not enabled,
        "warnings": (
            ["kakao_partial_set_both_or_neither"] if kakao == "partial" else []
        )
        + (["cd_already_enabled"] if enabled else []),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Check GitHub CD readiness (no secret values)")
    p.add_argument(
        "--dry-fixture",
        action="store_true",
        help="Do not call gh; print fixture evaluation only (tests)",
    )
    args = p.parse_args(argv)
    if args.dry_fixture:
        report = evaluate(secret_names=set(), variables={})
        print(json.dumps(report, ensure_ascii=False))
        return 1
    try:
        secrets = list_secret_names()
        variables = list_var_map()
    except (RuntimeError, json.JSONDecodeError, FileNotFoundError) as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        return 2
    report = evaluate(secret_names=secrets, variables=variables)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
