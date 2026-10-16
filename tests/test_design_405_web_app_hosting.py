"""design/405 - the server hosts the Flutter web app at /app/ and the web app logs in."""

from __future__ import annotations

import http.server
import importlib.util
import json
import sys
import threading
import urllib.request
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sentence_reading.llm import auth_magic_link as ml
from sentence_reading.llm.login_required import is_login_public_path

ROOT = Path(__file__).resolve().parent.parent


def _load(rel: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


@pytest.fixture()
def magic_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ASR_EMAIL_AUTH", "1")
    monkeypatch.setenv("ASR_EMAIL_MAGIC_LINK", "1")
    monkeypatch.setenv("ASR_AUTH_SECRET", "test-magic-secret")
    monkeypatch.setattr("sentence_reading.cache.paper_cache.project_root", lambda: tmp_path)
    monkeypatch.setattr("sentence_reading.llm.auth_accounts.project_root", lambda: tmp_path)
    monkeypatch.setattr(ml, "project_root", lambda: tmp_path)
    monkeypatch.setattr(ml, "_push", lambda *a, **k: None)
    monkeypatch.setattr(ml, "_pull", lambda *a, **k: None)
    yield tmp_path


def test_app_shell_is_public_but_its_neighbours_are_not():
    assert is_login_public_path("/app")
    assert is_login_public_path("/app/")
    assert is_login_public_path("/app/main.dart.js")
    assert is_login_public_path("/app/assets/fonts/MaterialIcons-Regular.otf")
    assert not is_login_public_path("/apple")
    assert not is_login_public_path("/application/x")
    assert not is_login_public_path("/api/library")


def test_bad_link_lands_on_the_page_that_asked(magic_env: Path):
    from sentence_reading.api import app as app_mod

    client = TestClient(app_mod.app)
    r = client.get("/api/auth/email/magic/open?t=nope&land=app", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("/app/?auth_error=")
    assert "asr_session=" not in (r.headers.get("set-cookie") or "")
    r = client.get("/api/auth/email/magic/open?t=nope", follow_redirects=False)
    assert r.headers["location"].startswith("/?auth_error=")


def test_good_link_for_web_app_sets_cookie_and_lands_on_app(magic_env: Path):
    from sentence_reading.api import app as app_mod

    client = TestClient(app_mod.app)
    minted = ml.mint_magic_token("webapp@example.com")
    r = client.get(f"/api/auth/email/magic/open?t={minted['token']}&land=app", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/app/?auth=logged_in"
    cookie = r.headers.get("set-cookie") or ""
    assert "asr_session=" in cookie
    assert "path=/" in cookie.lower()


def test_web_app_client_gets_land_app_link(magic_env: Path, monkeypatch: pytest.MonkeyPatch):
    from sentence_reading.api import app as app_mod

    sent: list[str] = []
    monkeypatch.setattr("sentence_reading.llm.email_smtp.smtp_configured", lambda: True)
    monkeypatch.setattr(
        "sentence_reading.llm.email_smtp.send_magic_link_email",
        lambda *, to_email, open_url: sent.append(open_url),
    )
    client = TestClient(app_mod.app)
    for hint in ("web_app", "android", "web"):
        r = client.post("/api/auth/email/magic/request", json={"email": f"{hint}@example.com", "client": hint})
        assert r.status_code == 200
    web_app, android, web = sent
    assert "&land=app" in web_app and "&mobile=1" not in web_app
    assert "&mobile=1" in android and "&land=app" not in android
    assert "&land=" not in web and "&mobile=1" not in web


def test_web_app_files_are_revalidated_and_not_indexed(tmp_path: Path):
    from sentence_reading.api import app as app_mod

    (tmp_path / "index.html").write_text("<html>shell</html>", encoding="utf-8")
    (tmp_path / "main.dart.js").write_text("void 0;", encoding="utf-8")
    probe = FastAPI()
    probe.mount("/app", app_mod._WebAppFiles(directory=tmp_path, html=True), name="web_app")
    client = TestClient(probe)
    r = client.get("/app/")
    assert r.status_code == 200 and "shell" in r.text
    assert r.headers["cache-control"] == "no-cache"
    assert "noindex" in r.headers.get("x-robots-tag", "")
    assert client.get("/app/main.dart.js").headers["cache-control"] == "no-cache"


def test_server_mounts_web_app_only_when_built_and_ships_it():
    src = _read("src/sentence_reading/api/app.py")
    assert 'if (_WEB_APP_DIR / "index.html").is_file():' in src
    assert 'app.mount("/app", _WebAppFiles(' in src
    assert '"web_app/**/*"' in _read("pyproject.toml")
    ignore = _read(".gcloudignore").splitlines()
    assert ignore.index("!src/sentence_reading/web_app/**") > ignore.index("*.png")


def test_web_client_uses_page_origin_and_browser_cookie():
    config = _read("mobile/lib/config.dart")
    assert "if (kIsWeb) return Uri.base.origin;" in config
    client = _read("mobile/lib/api/client.dart")
    assert "const String kMagicLinkClient = kIsWeb ? 'web_app' : 'android';" in client
    assert "'client': 'android'" not in client
    assert client.count("'client': kMagicLinkClient") == 2
    assert "if (!kIsWeb && token != null && token.isNotEmpty) {" in client


def _fake_build(root: Path, base: str = "/app/") -> Path:
    build = root / "build"
    (build / "canvaskit").mkdir(parents=True)
    (build / "assets").mkdir()
    (build / "index.html").write_text(f'<base href="{base}">', encoding="utf-8")
    (build / "version.json").write_text(json.dumps({"version": "9.9.9"}), encoding="utf-8")
    (build / "assets" / "a.bin").write_bytes(b"x")
    (build / "canvaskit" / "canvaskit.wasm").write_bytes(b"big")
    (build / ".last_build_id").write_text("id", encoding="utf-8")
    return build


def test_build_copy_drops_canvaskit_and_needs_app_base(tmp_path: Path):
    mod = _load("scripts/build_web_app.py", "build_web_app_405")
    dest = tmp_path / "web_app"
    (dest / "old").mkdir(parents=True)
    (dest / "old" / "stale.js").write_text("old", encoding="utf-8")
    n = mod.sync(_fake_build(tmp_path), dest)
    assert n == 3
    assert not (dest / "canvaskit").exists() and not (dest / ".last_build_id").exists()
    assert not (dest / "old").exists()
    assert mod.web_app_version(dest) == "9.9.9"
    with pytest.raises(SystemExit):
        mod.sync(_fake_build(tmp_path / "root", base="/"), tmp_path / "other")


def test_probe_serves_under_prefix(tmp_path: Path):
    mod = _load("scripts/web_probe.py", "web_probe_405")
    (tmp_path / "index.html").write_text("shell", encoding="utf-8")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), mod._handler(tmp_path, "/app/", None))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        assert urllib.request.urlopen(base + "/app/index.html", timeout=5).read() == b"shell"
        assert urllib.request.urlopen(base + "/app", timeout=5).geturl().endswith("/app/")
    finally:
        server.shutdown()


def test_ship_click_refuses_stale_web_app():
    src = _read("click/_run.py")
    ship = src[src.index("def job_ship_install"):src.index("def job_web_build")]
    assert ship.index("web_app_version()") < ship.index("session_freshness_guard.py")
    web = src[src.index("def job_web_build"):src.index("def job_selftest")]
    assert "scripts/build_web_app.py" in web and '"--app"' in web
    assert 's["cors"]' in web
