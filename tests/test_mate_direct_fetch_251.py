"""design/251 Phase A — mate resolve + SI status contract tests."""
from __future__ import annotations

from pathlib import Path

from sentence_reading.llm.mate_resolve import (
    _acs_si_candidates,
    extract_acs_si_stem,
    mate_direct_fetch_enabled,
    normalize_doi,
    resolve_mate,
)

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "sentence_reading" / "api" / "app.py"
EV_PY = ROOT / "src" / "sentence_reading" / "llm" / "evidence_kinds.py"
EV_DART = ROOT / "mobile" / "lib" / "services" / "evidence_kinds.dart"
SCREEN = ROOT / "mobile" / "lib" / "screens" / "pdf_import_screen.dart"
CTRL = ROOT / "mobile" / "lib" / "state" / "library_controller.dart"
VALIDATE = ROOT / "mobile" / "lib" / "mate_fetch" / "validate.dart"


def test_normalize_strips_acs_suppl_file() -> None:
    assert (
        normalize_doi("10.1021/acsami.2c04149/suppl_file/am2c04149_si_001.pdf")
        == "10.1021/acsami.2c04149"
    )


def test_acs_si_stem_and_candidates() -> None:
    stem = extract_acs_si_stem(
        "https://pubs.acs.org/doi/suppl/10.1021/acscatal.2c02045/suppl_file/cs2c02045_si_001.pdf"
    )
    assert stem == "cs2c02045"
    urls = _acs_si_candidates("10.1021/acscatal.2c02045", si_stem=stem)
    assert any(u.endswith("cs2c02045_si_001.pdf") for u in urls)


def test_resolve_bad_doi() -> None:
    r = resolve_mate("not-a-doi", "si")
    assert r["ok"] is False
    assert r["error"] == "bad_doi"


def test_kill_switch_env(monkeypatch) -> None:
    monkeypatch.setenv("ASR_MATE_DIRECT_FETCH", "0")
    assert mate_direct_fetch_enabled() is False
    r = resolve_mate("10.1021/acscatal.2c02045", "main")
    assert r["ok"] is True
    assert r["enabled"] is False
    assert r["candidates"] == []
    assert "doi.org" in r["fallback_browser"]


def test_route_and_status_wired() -> None:
    app = APP.read_text(encoding="utf-8")
    assert "/api/mate/resolve" in app
    assert "mate_direct_fetch" in app
    assert "mobile_mate_direct_fetch" in app
    assert 'version="0.3.246"' in app


def test_evidence_kinds() -> None:
    for path in (EV_PY, EV_DART):
        text = path.read_text(encoding="utf-8")
        for kind in (
            "mate_fetch_start",
            "mate_fetch_candidate",
            "mate_fetch_validate",
            "mate_fetch_done",
            "mate_fetch_fallback_browser",
            "mate_si_status",
        ):
            assert kind in text


def test_mobile_wire() -> None:
    screen = SCREEN.read_text(encoding="utf-8")
    ctrl = CTRL.read_text(encoding="utf-8")
    validate = VALIDATE.read_text(encoding="utf-8")
    assert "SI 없음" in screen
    assert "fetchMateForEntry" in screen
    assert "fetchMateForEntry" in ctrl
    assert "writeBytesIntoTree" in ctrl
    assert "kMateFetchMaxBytes" in validate
    assert "mateHostAllowed" in validate


def test_si_returns_acs_candidates_even_if_unverified() -> None:
    """Cloudflare on server must not wipe device candidates (0.3.244)."""
    from sentence_reading.llm.mate_resolve import resolve_mate

    r = resolve_mate("10.1021/acscatal.2c02045", "si", si_stem="cs2c02045")
    assert r["ok"] is True
    urls = [c.get("url", "") for c in (r.get("candidates") or [])]
    assert any("cs2c02045_si_001.pdf" in u for u in urls)


def test_rsc_and_nature_pattern_urls() -> None:
    from sentence_reading.llm.mate_resolve import pattern_si_candidates

    rsc = pattern_si_candidates("10.1039/d4se00467a")
    assert any("suppdata" in (c.get("url") or "") for c in rsc)
    nat = pattern_si_candidates("10.1038/s41929-026-01513-y")
    assert any("MOESM1_ESM.pdf" in (c.get("url") or "") and "2026" in (c.get("url") or "") for c in nat)
