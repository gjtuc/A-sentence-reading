#!/usr/bin/env python3
"""Session-start freshness — other chats must not work on a stale ASR tree.

  cd A-sentence-reading
  python scripts/session_freshness_guard.py

Exit 0: local semver >= live and (on main) not behind origin/main.
Exit 1: MUST pull / stop product deploy work (local < live or git behind).
Exit 2: misconfig / live unreachable (fail closed for agents).

Uses --allow-same-version + allow-dirty (session start ≠ deploy).
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "pre_deploy_guard.py"
SERVICE = os.environ.get("ASR_CLOUD_RUN_SERVICE") or "asr-sentence-reading"
REGION = os.environ.get("ASR_CLOUD_RUN_REGION") or "asia-northeast3"
PROJECT = os.environ.get("GCP_PROJECT_ID") or "peaceful-basis-503207-t4"


def parse_service(desc: dict[str, Any]) -> dict[str, str] | None:
    """The serving revision's release env, or None when it is not certain."""
    st = desc.get("status") or {}
    ready = st.get("latestReadyRevisionName")
    if not ready or ready != st.get("latestCreatedRevisionName"):
        return None
    traffic = st.get("traffic") or []
    if not any(t.get("latestRevision") and int(t.get("percent") or 0) == 100 for t in traffic):
        return None
    try:
        container = desc["spec"]["template"]["spec"]["containers"][0]
    except (KeyError, IndexError, TypeError):
        return None
    env = {e.get("name"): e.get("value") for e in container.get("env") or [] if isinstance(e, dict)}
    version = str(env.get("ASR_RELEASE_VERSION") or "").strip()
    if not version:
        return None
    return {"version": version, "deploy_git_sha": str(env.get("ASR_DEPLOY_GIT_SHA") or "").strip()}


def live_from_service(run=subprocess.run) -> dict[str, str] | None:
    """design/396 — ask Cloud Run, not the app, so a scaled-to-zero API stays asleep."""
    exe = "gcloud.cmd" if os.name == "nt" else "gcloud"
    try:
        res = run(
            [exe, "run", "services", "describe", SERVICE, "--region", REGION,
             "--project", PROJECT, "--format=json"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )
    except Exception:  # noqa: BLE001
        return None
    if res.returncode != 0:
        return None
    try:
        desc = json.loads(res.stdout or "{}")
    except json.JSONDecodeError:
        return None
    return parse_service(desc) if isinstance(desc, dict) else None


def _load_guard():
    spec = importlib.util.spec_from_file_location("pre_deploy_guard", GUARD)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot_load:{GUARD}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main(argv: list[str] | None = None) -> int:
    _ = argv
    if os.environ.get("ASR_SKIP_DEPLOY_GUARD", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        print(
            json.dumps(
                {"ok": True, "skipped": True, "must_pull": False},
                ensure_ascii=False,
            )
        )
        return 0

    live = None
    if (os.environ.get("ASR_FRESHNESS_LIVE") or "").strip().lower() != "http":
        live = live_from_service()
    try:
        mod = _load_guard()
        plan = mod.run_guard(
            allow_same_version=True,
            allow_dirty=True,
            skip_fetch=False,
            live_data=live,
        )
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "ok": False,
                    "must_pull": False,
                    "action": "abort",
                    "errors": [f"session_guard_failed:{type(exc).__name__}:{exc}"],
                },
                ensure_ascii=False,
            )
        )
        return 2

    errs = list(plan.get("errors") or [])
    stale = [
        e
        for e in errs
        if e.startswith("local_version_downgrade")
        or e.startswith("git_behind_remote")
        or e.startswith("live_status_fetch_failed")
        or e.startswith("local_app_version_missing")
        or e.startswith("semver_parse")
        or e.startswith("git_fetch_failed")
        or e.startswith("not_a_git_repo")
        or e.startswith("remote_ref_missing")
    ]
    must_pull = any(
        e.startswith("local_version_downgrade") or e.startswith("git_behind_remote")
        for e in stale
    )
    out = {
        "ok": not stale,
        "must_pull": must_pull,
        "action": "pull_first" if must_pull else ("allow" if not stale else "abort"),
        "errors": stale,
        "local_version": plan.get("local_version"),
        "mobile_version": plan.get("mobile_version"),
        "live_version": plan.get("live_version"),
        "live_deploy_sha": plan.get("live_deploy_sha"),
        "live_source": "service_env" if live else "http",
        "git_head": plan.get("git_head"),
        "git_branch": plan.get("git_branch"),
        "commits_behind_remote": plan.get("commits_behind_remote"),
        "detail": (
            "STALE: git fetch && git pull --ff-only origin main before any "
            "product edit/deploy. Do not cover live with an older chat."
            if must_pull
            else (
                "ok - local >= live; still bump above live before deploy"
                if not stale
                else "abort - fix errors before product work"
            )
        ),
    }
    print(json.dumps(out, ensure_ascii=True))
    if must_pull:
        return 1
    if stale:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
