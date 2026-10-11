"""design/395 — the API scales to zero and loads the phoneme model as it starts."""

from __future__ import annotations

from pathlib import Path

from sentence_reading.api import app as app_mod

ROOT = Path(__file__).resolve().parents[1]


def test_api_min_instances_default_is_zero() -> None:
    src = (ROOT / "scripts" / "deploy_cloud_run.sh").read_text(encoding="utf-8")
    assert '--min-instances "${ASR_MIN_INSTANCES:-0}"' in src
    assert "ASR_MIN_INSTANCES:-1" not in src


def test_api_memory_default_is_6gi() -> None:
    src = (ROOT / "scripts" / "deploy_cloud_run_pair.sh").read_text(encoding="utf-8")
    assert 'ASR_CLOUD_RUN_MEMORY="${ASR_API_MEMORY:-6Gi}"' in src


def test_worker_stays_at_zero() -> None:
    src = (ROOT / "scripts" / "deploy_cloud_run_worker.sh").read_text(encoding="utf-8")
    assert 'ASR_MIN_INSTANCES="${ASR_WORKER_MIN_INSTANCES:-0}"' in src


def test_preload_only_on_cloud_run_api(monkeypatch) -> None:
    monkeypatch.delenv("ASR_HEAR_PRELOAD", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("ASR_SERVICE_ROLE", raising=False)
    assert app_mod._hear_preload_on_boot() is False

    monkeypatch.setenv("K_SERVICE", "asr-sentence-reading")
    assert app_mod._hear_preload_on_boot() is True

    monkeypatch.setenv("ASR_SERVICE_ROLE", "worker")
    assert app_mod._hear_preload_on_boot() is False


def test_preload_switch_wins(monkeypatch) -> None:
    monkeypatch.setenv("K_SERVICE", "asr-sentence-reading")
    monkeypatch.setenv("ASR_SERVICE_ROLE", "api")
    monkeypatch.setenv("ASR_HEAR_PRELOAD", "0")
    assert app_mod._hear_preload_on_boot() is False

    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.setenv("ASR_HEAR_PRELOAD", "1")
    assert app_mod._hear_preload_on_boot() is True


def test_preload_writes_boot_warm_row(monkeypatch) -> None:
    import sentence_reading.llm.hear_waveform as hw

    seen: list[tuple[str, dict]] = []
    monkeypatch.setattr(hw, "warm_report", lambda: {"warm_ok": 1, "warm_ms": 21000, "warm_detail": "none"})
    monkeypatch.setattr(app_mod, "_emit_hear_row", lambda route, report: seen.append((route, report)))
    app_mod._preload_hear()
    assert seen == [("boot_warm", {"warm_ok": 1, "warm_ms": 21000, "warm_detail": "none"})]


def test_preload_swallows_failure(monkeypatch) -> None:
    import sentence_reading.llm.hear_waveform as hw

    def boom() -> dict:
        raise RuntimeError("no model")

    monkeypatch.setattr(hw, "warm_report", boom)
    app_mod._preload_hear()


def test_lifespan_starts_preload_thread() -> None:
    src = (ROOT / "src" / "sentence_reading" / "api" / "app.py").read_text(encoding="utf-8")
    head = src.split("app = FastAPI(", 1)[0]
    assert "_hear_preload_on_boot()" in head
    assert 'name="hear-preload"' in head
