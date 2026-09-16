"""Upload ASR runtime secrets to a private bucket. Prints names and sizes only."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sentence_reading.llm.gcs_secrets import (  # noqa: E402
    ALLOWLIST,
    BUCKET,
    ENV_OBJECT,
    fetch_runtime,
    public_members,
    select_runtime,
    upload_runtime,
)

ENV_FILE = Path(r"D:\.cursor\gc-home\gc_automation.env")
REGION = "asia-northeast3"
SERVICES = ("asr-sentence-reading", "asr-sentence-reading-worker")


def _gcloud() -> str:
    candidates = [
        Path(r"C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"),
        Path(r"C:\Program Files\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"),
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    raise FileNotFoundError("gcloud.cmd missing")


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, val = s.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and val:
            out[key] = val
    return out


def _cloud_run_env() -> dict[str, str]:
    """Names already on live. Values are not printed."""
    merged: dict[str, str] = {}
    gcloud = _gcloud()
    for service in SERVICES:
        try:
            raw = subprocess.check_output(
                [
                    gcloud,
                    "run",
                    "services",
                    "describe",
                    service,
                    "--region",
                    REGION,
                    "--project",
                    "peaceful-basis-503207-t4",
                    "--format=json",
                ],
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError:
            print("cloud_run_skip", service)
            continue
        doc = json.loads(raw)
        containers = (
            doc.get("spec", {})
            .get("template", {})
            .get("spec", {})
            .get("containers")
            or []
        )
        env = containers[0].get("env") if containers else []
        for item in env or []:
            name = str(item.get("name") or "")
            if name not in ALLOWLIST or name in merged:
                continue
            if item.get("valueFrom"):
                print("cloud_run_secret_ref", name)
                continue
            val = str(item.get("value") or "").strip()
            if val:
                merged[name] = val
    return merged


def _secret_value(name: str) -> str:
    """Secret Manager payload. Caller must not print it."""
    try:
        raw = subprocess.check_output(
            [
                _gcloud(),
                "secrets",
                "versions",
                "access",
                "latest",
                f"--secret={name}",
                "--project=peaceful-basis-503207-t4",
            ],
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        print("secret_manager_skip", name)
        return ""
    return raw.decode("utf-8", errors="replace").strip()


def _ensure_bucket() -> None:
    gcloud = _gcloud()
    desc = subprocess.run(
        [gcloud, "storage", "buckets", "describe", f"gs://{BUCKET}", "--format=json"],
        capture_output=True,
    )
    if desc.returncode != 0:
        created = subprocess.run(
            [
                gcloud,
                "storage",
                "buckets",
                "create",
                f"gs://{BUCKET}",
                "--location=asia-northeast3",
                "--uniform-bucket-level-access",
                "--public-access-prevention",
                "--project=peaceful-basis-503207-t4",
            ],
            capture_output=True,
            text=True,
        )
        if created.returncode != 0:
            err = (created.stderr or created.stdout or "").strip().splitlines()
            print("bucket_create_failed", err[-1] if err else "unknown")
            raise SystemExit(1)
        print("bucket_created", BUCKET)
    again = subprocess.check_output(
        [gcloud, "storage", "buckets", "describe", f"gs://{BUCKET}", "--format=json"]
    )
    meta = json.loads(again)
    iam = meta.get("iamConfiguration") or meta.get("iam_configuration") or {}
    pap = str(
        meta.get("public_access_prevention")
        or iam.get("publicAccessPrevention")
        or iam.get("public_access_prevention")
        or ""
    )
    uniform = meta.get("uniform_bucket_level_access")
    if uniform is None:
        nested = iam.get("uniformBucketLevelAccess") or iam.get("uniform_bucket_level_access") or {}
        uniform = nested.get("enabled") if isinstance(nested, dict) else nested
    print("pap", pap or "missing", "uniform", uniform)
    if pap != "enforced" or not uniform:
        print("bucket_not_private_enough")
        raise SystemExit(1)
    policy_raw = subprocess.check_output(
        [gcloud, "storage", "buckets", "get-iam-policy", f"gs://{BUCKET}", "--format=json"]
    )
    policy = json.loads(policy_raw)
    public = public_members(policy)
    print("public_bindings", "none" if not public else ",".join(public))
    if public:
        raise SystemExit(1)
    viewers = [
        b.get("role")
        for b in policy.get("bindings") or []
        if any(str(m).startswith("projectViewer:") for m in (b.get("members") or []))
        and "Object" in str(b.get("role") or "")
    ]
    if viewers:
        print("project_viewer_can_read_objects")
        gcloud = _gcloud()
        removed = subprocess.run(
            [
                gcloud,
                "storage",
                "buckets",
                "remove-iam-policy-binding",
                f"gs://{BUCKET}",
                "--member=projectViewer:peaceful-basis-503207-t4",
                "--role=roles/storage.legacyObjectReader",
            ],
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [
                gcloud,
                "storage",
                "buckets",
                "remove-iam-policy-binding",
                f"gs://{BUCKET}",
                "--member=projectViewer:peaceful-basis-503207-t4",
                "--role=roles/storage.legacyBucketReader",
            ],
            capture_output=True,
            text=True,
        )
        if removed.returncode != 0:
            print("viewer_unbind_failed")
            raise SystemExit(1)
        print("project_viewer_unbound")


def main() -> int:
    cred = (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    if cred and not Path(cred).is_file():
        os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
    local = _parse_env_file(ENV_FILE)
    if not local:
        print("env_file_missing")
        return 1
    cloud = _cloud_run_env()
    for env_name, secret_name in (
        ("ASR_SMTP_USER", "st-auth-smtp-user"),
        ("ASR_SMTP_PASS", "st-auth-smtp-password"),
    ):
        if not cloud.get(env_name):
            val = _secret_value(secret_name)
            if val:
                cloud[env_name] = val
                print("filled_secret_ref", env_name)
    # Local file wins when both have a value. Cloud Run fills keys this PC file lacks.
    merged = dict(cloud)
    merged.update(select_runtime(local))
    _ensure_bucket()
    sizes = upload_runtime(merged)
    got = fetch_runtime()
    print("bucket", BUCKET)
    print("object", ENV_OBJECT, "bytes", sizes.get(ENV_OBJECT, 0), "keys", len(got))
    print("key_names", " ".join(k for k in ALLOWLIST if k in got))
    absent = [
        k
        for k in (
            "GEMINI_API_KEY",
            "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT",
            "AZURE_DOCUMENT_INTELLIGENCE_KEY",
            "ASR_AUTH_SECRET",
            "ASR_GOOGLE_CLIENT_ID",
        )
        if k not in got
    ]
    if absent:
        print("missing", ",".join(absent))
        return 1
    filled = [k for k in got if k not in local]
    if filled:
        print("filled_from_cloud_run", " ".join(filled))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
