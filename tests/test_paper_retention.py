"""design/144 — paper retention TTL rules."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from sentence_reading.llm import paper_retention as pr


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def test_default_and_extend_window() -> None:
    now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    entry = {"expires_at": _iso(now + timedelta(days=20))}
    assert pr.can_extend_retention(entry, now=now + timedelta(days=1)) is True
    assert pr.can_extend_retention(entry, now=now + timedelta(days=19)) is True
    assert pr.can_extend_retention(entry, now=now + timedelta(days=21)) is False
    out = pr.extend_retention(entry, now=now)
    assert pr.expires_at_dt(out) == now + timedelta(days=20 + pr.EXTEND_DAYS)


def test_reading_grace_once_per_expiry() -> None:
    exp = datetime(2026, 8, 1, tzinfo=timezone.utc)
    entry = {"expires_at": _iso(exp)}
    now = exp + timedelta(hours=1)
    graced, ok = pr.apply_reading_grace(entry, now=now)
    assert ok is True
    assert pr.expires_at_dt(graced) == exp + timedelta(days=pr.READING_GRACE_DAYS)
    _, ok2 = pr.apply_reading_grace(graced, now=now)
    assert ok2 is False


def test_reading_grace_again_after_new_expiry() -> None:
    exp1 = datetime(2026, 8, 1, tzinfo=timezone.utc)
    entry = {"expires_at": _iso(exp1)}
    graced, _ = pr.apply_reading_grace(entry, now=exp1 + timedelta(hours=1))
    exp2 = pr.expires_at_dt(graced)
    assert exp2 is not None
    graced2, ok = pr.apply_reading_grace(graced, now=exp2 + timedelta(hours=1))
    assert ok is True
    assert pr.expires_at_dt(graced2) == exp2 + timedelta(days=pr.READING_GRACE_DAYS)


def test_kill_switch() -> None:
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("ASR_PAPER_RETENTION", "0")
    entry = {"expires_at": _iso(datetime(2020, 1, 1, tzinfo=timezone.utc))}
    assert pr.retention_enabled() is False
    assert pr.is_expired(entry) is False
    monkeypatch.delenv("ASR_PAPER_RETENTION", raising=False)


def test_api_wiring_status() -> None:
    from fastapi.testclient import TestClient

    from sentence_reading.api.app import app

    st = TestClient(app).get("/api/status").json()
    assert st["version"] == "0.3.78"
    assert st["paper_retention"] is True
    assert st["paper_retention_days"] == 90
    assert st["paper_retention_extend_days"] == 90
    assert st["paper_retention_reading_grace_days"] == 3


def test_extend_retention_api(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST extend-retention: allowed in warn window; 409 outside; 404 missing."""
    from fastapi.testclient import TestClient

    from sentence_reading.api import app as app_mod

    now = datetime.now(timezone.utc)
    cid = "retentiontest01"
    entry = {"id": cid, "expires_at": _iso(now + timedelta(days=20))}
    store: dict[str, dict] = {cid: dict(entry)}

    monkeypatch.setenv("ASR_ACCESS_GATE", "0")
    monkeypatch.setattr(
        app_mod,
        "get_index_entry",
        lambda cache_id: store.get(str(cache_id or "").strip()),
    )
    monkeypatch.setattr(
        app_mod,
        "patch_index_entry",
        lambda cache_id, patch: store.setdefault(str(cache_id).strip(), {}).update(patch)
        or store[str(cache_id).strip()],
    )

    client = TestClient(app_mod.app)
    ok = client.post(f"/api/cache/papers/{cid}/extend-retention")
    assert ok.status_code == 200
    body = ok.json()
    assert body["ok"] is True
    assert body["retention"]["enabled"] is True
    assert pr.expires_at_dt(store[cid]) == now + timedelta(days=20 + pr.EXTEND_DAYS)

    far = {"id": "far001", "expires_at": _iso(now + timedelta(days=60))}
    store["far001"] = far
    deny = client.post("/api/cache/papers/far001/extend-retention")
    assert deny.status_code == 409
    assert deny.json()["error"] == "extend_not_allowed"

    miss = client.post("/api/cache/papers/missing0001/extend-retention")
    assert miss.status_code == 404
    assert miss.json()["error"] == "cache_not_found"

    monkeypatch.setenv("ASR_PAPER_RETENTION", "0")
    off = client.post(f"/api/cache/papers/{cid}/extend-retention")
    assert off.status_code == 404
    assert off.json()["error"] == "retention_disabled"


def test_mobile_retention_wiring() -> None:
    """design/144 — library ⚠️ + extend client wiring."""
    import os

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    screen = open(
        os.path.join(root, "mobile", "lib", "screens", "library_screen.dart"),
        encoding="utf-8",
    ).read()
    client = open(
        os.path.join(root, "mobile", "lib", "api", "client.dart"),
        encoding="utf-8",
    ).read()
    ctrl = open(
        os.path.join(root, "mobile", "lib", "state", "library_controller.dart"),
        encoding="utf-8",
    ).read()
    models = open(
        os.path.join(root, "mobile", "lib", "api", "paper_models.dart"),
        encoding="utf-8",
    ).read()
    design = open(
        os.path.join(root, "docs", "design", "144-paper-retention-ttl.md"),
        encoding="utf-8",
    ).read()
    assert "warning_amber_rounded" in screen
    assert "_showRetentionSheet" in screen
    assert "extendPaperRetention" in client
    assert "extendRetention" in ctrl
    assert "retentionWarn" in models
    assert "0.3.60" in design
    app_src = open(
        os.path.join(root, "src", "sentence_reading", "api", "app.py"),
        encoding="utf-8",
    ).read()
    idx = app_src.find("def cache_extend_retention")
    assert idx > 0
    assert "_paid_access_denied" in app_src[idx : idx + 400]
