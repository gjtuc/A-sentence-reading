"""design/319 — auth/access route tables leave FastAPI app."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.api.routes import access as access_routes
from sentence_reading.api.routes import auth as auth_routes

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src/sentence_reading/api/app.py"
DEPS = ROOT / "src/sentence_reading/api/deps.py"
DESIGN = ROOT / "docs/design/319-auth-access-routers.md"
README = ROOT / "docs/design/README.md"


def test_design_319_locked() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "Status: **locked" in text
    assert "deps.py" in text
    assert "include_router" in text
    assert "319-auth-access-routers.md" in README.read_text(encoding="utf-8")


def test_app_py_no_longer_owns_auth_access_decorators() -> None:
    src = APP.read_text(encoding="utf-8")
    assert '@app.get("/api/auth/' not in src
    assert '@app.post("/api/auth/' not in src
    assert '@app.get("/api/access/' not in src
    assert '@app.post("/api/access/' not in src
    assert "@auth_routes.router.get" in src
    assert "@access_routes.router.get" in src
    assert "include_router(auth_routes.router)" in src
    assert "include_router(access_routes.router)" in src
    deps = DEPS.read_text(encoding="utf-8")
    assert "def paid_access_denied" in deps
    assert "def request_user" in deps
    assert "def is_admin_user" in deps


def test_auth_and_access_paths_are_mounted() -> None:
    auth_paths = {getattr(r, "path", "") for r in auth_routes.router.routes}
    access_paths = {getattr(r, "path", "") for r in access_routes.router.routes}
    assert "/api/auth/status" in auth_paths
    assert "/api/auth/logout" in auth_paths
    assert "/api/access/status" in access_paths
    assert "/api/access/invite" in access_paths
    client = TestClient(app)
    st = client.get("/api/auth/status").json()
    assert st.get("ok") is True
    acc = client.get("/api/access/status").json()
    assert acc.get("ok") is True or "access" in acc or "error" in acc
