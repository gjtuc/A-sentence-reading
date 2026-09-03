#!/usr/bin/env python3
"""Cursor beforeShellExecution — deny stale ASR Cloud Run deploys (design/155).

Reads hook JSON from stdin; prints one permission JSON line (failClosed-safe).
Invokes scripts/pre_deploy_guard.py against the ASR worktree from cwd/command.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
from pathlib import Path

DEFAULT_ASR = Path(
    os.environ.get(
        "ASR_REPO",
        r"C:\Users\user\Desktop\.cursor\repos\A-sentence-reading",
    )
)

DEPLOY_PAT = re.compile(
    r"(?:^|[\s;|&])(?:bash\s+|sh\s+)?(?:\.?/?)*(?:scripts/)?deploy_cloud_run\.(?:sh|ps1)"
    r"|(?:^|[\s;|&])gcloud(?:\.cmd)?\s+run\s+deploy\b"
    r"|(?:^|[\s;|&])gcloud(?:\.cmd)?\s+run\s+services\s+replace\b",
    re.I,
)
ASRISH = re.compile(
    r"A-sentence-reading|asr-sentence-reading|sentence_reading[/\\]|ASR_",
    re.I,
)
STOCKISH = re.compile(
    r"repos[/\\]+stock\b|stock_trading|st-trading-ui|ST_SKIP_DEPLOY_GUARD|ST_DEPLOY_",
    re.I,
)


def emit(payload: dict) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    sys.stdout.flush()
    return 0


def _find_asr_root(command: str, cwd: str) -> Path | None:
    blob = f"{command}\n{cwd}"
    # Explicit path in command/cwd.
    m = re.search(
        r"([A-Za-z]:[\\/][^\s\"']*A-sentence-reading|/c/[^\s\"']*A-sentence-reading|"
        r"~/[^\s\"']*A-sentence-reading)",
        blob,
        re.I,
    )
    if m:
        p = Path(m.group(1).replace("/c/", "C:/"))
        if (p / "scripts" / "pre_deploy_guard.py").is_file():
            return p
    for candidate in (Path(cwd) if cwd else None, DEFAULT_ASR):
        if candidate is None:
            continue
        try:
            cur = candidate.resolve()
        except OSError:
            continue
        for _ in range(6):
            if (cur / "scripts" / "pre_deploy_guard.py").is_file() and (
                cur / "src" / "sentence_reading" / "api" / "app.py"
            ).is_file():
                return cur
            if cur.parent == cur:
                break
            cur = cur.parent
    if (DEFAULT_ASR / "scripts" / "pre_deploy_guard.py").is_file():
        return DEFAULT_ASR
    return None


def _load_guard(root: Path):
    script = root / "scripts" / "pre_deploy_guard.py"
    spec = importlib.util.spec_from_file_location("asr_pre_deploy_guard", script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot_load:{script}")
    # Point module ROOT at this worktree.
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.ROOT = root
    mod.APP_PY = root / "src" / "sentence_reading" / "api" / "app.py"
    mod.PUBSPEC = root / "mobile" / "pubspec.yaml"
    mod.CONFIG_DART = root / "mobile" / "lib" / "config.dart"
    return mod


def main() -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return emit(
            {
                "permission": "deny",
                "user_message": "ASR deploy hook: invalid stdin JSON — blocked.",
                "agent_message": "hook_block_stale_asr_deploy: invalid stdin JSON",
            }
        )

    command = str(data.get("command") or "")
    cwd = str(
        data.get("working_directory")
        or data.get("cwd")
        or data.get("workdir")
        or ""
    )
    blob = f"{command} {cwd}"

    if not DEPLOY_PAT.search(command):
        return emit({"permission": "allow"})

    # Stock deploys are owned by the stock hook/router — do not double-deny here.
    if STOCKISH.search(blob) and not ASRISH.search(blob):
        return emit({"permission": "allow"})

    # Only claim ASR when path/service markers say so, or cwd is ASR worktree.
    root = _find_asr_root(command, cwd)
    if root is None and not ASRISH.search(blob):
        return emit({"permission": "allow"})
    if root is None:
        return emit(
            {
                "permission": "deny",
                "user_message": (
                    "ASR deploy blocked: cannot locate A-sentence-reading worktree "
                    "for pre_deploy_guard. cd to the repo first."
                ),
                "agent_message": "asr_worktree_missing",
            }
        )

    if os.environ.get("ASR_SKIP_DEPLOY_GUARD", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ) or re.search(r"ASR_SKIP_DEPLOY_GUARD\s*=\s*1", command):
        return emit(
            {
                "permission": "allow",
                "agent_message": (
                    "ASR_SKIP_DEPLOY_GUARD set — deploy allowed (emergency only)."
                ),
            }
        )

    try:
        # Ensure git commands run in the target worktree.
        os.chdir(root)
        mod = _load_guard(root)
        plan = mod.run_guard(skip_fetch=False, allow_dirty=False, allow_same_version=False)
    except Exception as exc:  # noqa: BLE001
        return emit(
            {
                "permission": "deny",
                "user_message": f"ASR deploy guard failed: {exc}",
                "agent_message": f"asr_deploy_guard_failed:{exc}",
            }
        )

    if plan.get("ok"):
        return emit(
            {
                "permission": "allow",
                "agent_message": (
                    f"ASR deploy ok local={plan.get('local_version')} "
                    f"live={plan.get('live_version')}"
                ),
            }
        )

    errs = list(plan.get("errors") or [])
    # Hook focuses on overwrite/stale; still surface all errors.
    msg = (
        "BLOCKED stale ASR deploy: "
        f"local={plan.get('local_version') or '?'} live={plan.get('live_version') or '?'} "
        f"behind={plan.get('commits_behind_remote') or 0}. "
        f"Errors: {'; '.join(errs[:4])}. "
        "git fetch && git pull --ff-only origin main, bump app.py+pubspec+config "
        "above live, commit, then redeploy. Emergency only: ASR_SKIP_DEPLOY_GUARD=1"
    )
    return emit(
        {
            "permission": "deny",
            "user_message": msg,
            "agent_message": msg,
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
