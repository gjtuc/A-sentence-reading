#!/usr/bin/env python3
"""
배포 전 가드 — live 버전 역행·stale git·버전 불일치 차단 (design/155).

다른 채팅/옛 워크트리가 Cloud Run live를 덮어쓰는 회귀 방지:
  1. 로컬 app 버전 < live 버전 → 거부 (downgrade deploy)
  2. origin/main 보다 뒤처진 HEAD → 거부 (git pull 먼저)
  3. app.py vs mobile/pubspec 버전 불일치 → 거부
  4. (선택) working tree dirty → 거부

환경 변수 우회 (비상만):
  ASR_SKIP_DEPLOY_GUARD=1        — 전체 가드 스킵
  ASR_DEPLOY_ALLOW_DIRTY=1      — uncommitted 허용
  ASR_DEPLOY_ALLOW_SAME_VERSION=1 — live와 같은 버전 재배포 허용
"""

from __future__ import annotations

import argparse
import json
import re
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
APP_PY = ROOT / "src" / "sentence_reading" / "api" / "app.py"
PUBSPEC = ROOT / "mobile" / "pubspec.yaml"
CONFIG_DART = ROOT / "mobile" / "lib" / "config.dart"
DEFAULT_STATUS_URL = (
    "https://asr-sentence-reading-984608876300.asia-northeast3.run.app/api/status"
)


def _run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd or ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def parse_semver(label: str) -> tuple[int, ...] | None:
    s = (label or "").strip()
    m = re.match(r"^(\d+(?:\.\d+)*)", s)
    if not m:
        return None
    parts: list[int] = []
    for piece in m.group(1).split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            return None
    return tuple(parts) if parts else None


def compare_semver(a: str, b: str) -> int | None:
    """Return -1 if a<b, 0 if equal, +1 if a>b; None if unparsable."""
    pa, pb = parse_semver(a), parse_semver(b)
    if pa is None or pb is None:
        return None
    n = max(len(pa), len(pb))
    pa = pa + (0,) * (n - len(pa))
    pb = pb + (0,) * (n - len(pb))
    if pa < pb:
        return -1
    if pa > pb:
        return 1
    return 0


def read_repo_app_version() -> str:
    text = APP_PY.read_text(encoding="utf-8")
    m = re.search(r'version="([^"]+)"', text)
    if m:
        return m.group(1)
    m = re.search(r'"version":\s*"([^"]+)"', text)
    return m.group(1) if m else ""


def read_pubspec_version() -> str:
    if not PUBSPEC.is_file():
        return ""
    for line in PUBSPEC.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^version:\s*(\S+)", line.strip())
        if m:
            return m.group(1).split("+")[0]
    return ""


def read_k_app_version_label() -> str:
    if not CONFIG_DART.is_file():
        return ""
    m = re.search(
        r"kAppVersionLabel\s*=\s*['\"]([^'\"]+)['\"]",
        CONFIG_DART.read_text(encoding="utf-8"),
    )
    return m.group(1).strip() if m else ""


def fetch_live_status(url: str, *, timeout: float = 60.0) -> dict[str, Any]:
    """HTTPS status JSON (verify_live_status.fetch_status 와 동일 계약)."""
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


def git_fetch(origin: str = "origin") -> list[str]:
    errs: list[str] = []
    if _run(["git", "rev-parse", "--git-dir"]).returncode != 0:
        errs.append("not_a_git_repo")
        return errs
    r = _run(["git", "fetch", origin, "--prune"])
    if r.returncode != 0:
        errs.append(f"git_fetch_failed:{(r.stderr or r.stdout or '').strip()[:200]}")
    return errs


def git_behind_remote(
    remote_ref: str = "origin/main",
) -> tuple[list[str], int]:
    """Returns (errors, commits_behind)."""
    errs: list[str] = []
    r = _run(["git", "rev-parse", "--verify", remote_ref])
    if r.returncode != 0:
        errs.append(f"remote_ref_missing:{remote_ref}")
        return errs, 0
    behind = _run(["git", "rev-list", "--count", f"HEAD..{remote_ref}"])
    if behind.returncode != 0:
        errs.append("git_behind_check_failed")
        return errs, 0
    try:
        n = int((behind.stdout or "0").strip() or "0")
    except ValueError:
        errs.append("git_behind_parse_failed")
        return errs, 0
    if n > 0:
        errs.append(f"git_behind_remote_by_{n}")
    return errs, n


def git_dirty() -> bool:
    # WHY: untracked QA/tmp 스크린샷은 배포 차단에 쓰지 않음 (-uno).
    r = _run(["git", "status", "--porcelain", "-uno"])
    if r.returncode != 0:
        return True
    return bool((r.stdout or "").strip())


def git_current_branch() -> str:
    r = _run(["git", "branch", "--show-current"])
    if r.returncode != 0:
        return ""
    return (r.stdout or "").strip()


def git_head_sha(short: bool = True) -> str:
    r = _run(["git", "rev-parse", "HEAD"])
    if r.returncode != 0:
        return ""
    sha = (r.stdout or "").strip()
    return sha[:12] if short and len(sha) > 12 else sha


def run_guard(
    *,
    status_url: str = DEFAULT_STATUS_URL,
    remote_ref: str = "origin/main",
    allow_dirty: bool = False,
    allow_same_version: bool = False,
    skip_fetch: bool = False,
    ci_mode: bool = False,
    live_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if ci_mode:
        allow_dirty = True
        allow_same_version = True
    errs: list[str] = []
    local_ver = read_repo_app_version()
    mobile_ver = read_pubspec_version()
    live_ver = ""
    live_sha = ""
    behind = 0

    if not local_ver:
        errs.append("local_app_version_missing")
    if mobile_ver and local_ver and mobile_ver != local_ver:
        errs.append(f"mobile_app_version_mismatch:{mobile_ver}_vs_{local_ver}")
    config_ver = read_k_app_version_label()
    if mobile_ver and config_ver and mobile_ver != config_ver:
        errs.append(f"mobile_config_version_mismatch:{config_ver}_vs_{mobile_ver}")

    try:
        live = live_data if live_data is not None else fetch_live_status(status_url)
        live_ver = str(live.get("version") or "")
        live_sha = str(live.get("deploy_git_sha") or live.get("deploy_sha") or "")
    except Exception as exc:  # noqa: BLE001
        errs.append(f"live_status_fetch_failed:{type(exc).__name__}")

    if local_ver and live_ver:
        cmp = compare_semver(local_ver, live_ver)
        if cmp is None:
            errs.append("semver_parse_failed")
        elif cmp < 0:
            errs.append(f"local_version_downgrade:{local_ver}_lt_live_{live_ver}")
        elif cmp == 0 and not allow_same_version:
            errs.append(f"same_version_redeploy_blocked:{local_ver}")

    if not skip_fetch and not ci_mode:
        errs.extend(git_fetch())
    branch = git_current_branch()
    if not ci_mode and branch in ("main", "master"):
        fetch_errs, behind = git_behind_remote(remote_ref)
        errs.extend(fetch_errs)
    else:
        behind = 0

    head_sha = git_head_sha()
    if live_sha and head_sha and live_sha.startswith(head_sha[:12]):
        # Already deployed this commit — block unless explicit same-version ok.
        if not allow_same_version:
            errs.append(f"already_deployed_sha:{head_sha}")

    if not allow_dirty and not ci_mode and git_dirty():
        errs.append("working_tree_dirty")

    mode = "ci" if ci_mode else "deploy"
    return {
        "ok": not errs,
        "mode": mode,
        "local_version": local_ver,
        "mobile_version": mobile_ver,
        "live_version": live_ver,
        "live_deploy_sha": live_sha,
        "git_head": head_sha,
        "git_branch": branch,
        "commits_behind_remote": behind,
        "remote_ref": remote_ref,
        "errors": errs,
    }


def main(argv: list[str] | None = None) -> int:
    if (Path(__file__).parent.parent / ".git").exists() is False:
        # EDGE: exported tarball — caller should not run guard.
        pass
    import os

    if os.environ.get("ASR_SKIP_DEPLOY_GUARD", "").strip() in ("1", "true", "yes"):
        print(json.dumps({"ok": True, "skipped": True}, ensure_ascii=False))
        return 0

    p = argparse.ArgumentParser(description="Pre-deploy guard (no live downgrade)")
    p.add_argument("--url", default=DEFAULT_STATUS_URL)
    p.add_argument("--remote-ref", default="origin/main")
    p.add_argument("--skip-fetch", action="store_true")
    p.add_argument(
        "--allow-same-version",
        action="store_true",
        help="allow redeploy when local version == live (default: block)",
    )
    p.add_argument(
        "--allow-dirty",
        action="store_true",
        help="allow uncommitted changes (default: block)",
    )
    p.add_argument(
        "--ci",
        action="store_true",
        help="CI/PR: only block live downgrade + version mismatch (no dirty/behind/same-version)",
    )
    args = p.parse_args(argv)

    ci_mode = bool(args.ci)
    allow_dirty = ci_mode or args.allow_dirty or os.environ.get(
        "ASR_DEPLOY_ALLOW_DIRTY", ""
    ) in (
        "1",
        "true",
        "yes",
    )
    allow_same = ci_mode or args.allow_same_version or os.environ.get(
        "ASR_DEPLOY_ALLOW_SAME_VERSION", ""
    ) in ("1", "true", "yes")

    result = run_guard(
        status_url=args.url,
        remote_ref=args.remote_ref,
        allow_dirty=allow_dirty,
        allow_same_version=allow_same,
        skip_fetch=bool(args.skip_fetch) or ci_mode,
        ci_mode=ci_mode,
    )
    print(json.dumps(result, ensure_ascii=False))
    if not result["ok"]:
        print(
            "DEPLOY BLOCKED — git pull, bump version above live, commit, then retry. "
            "Emergency: ASR_SKIP_DEPLOY_GUARD=1 (not recommended).",
            file=sys.stderr,
        )
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
