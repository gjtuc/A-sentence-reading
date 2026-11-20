"""design/510 — one Azure prebuilt-layout analyze per uploaded file."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from sentence_reading.pdf import layout_map as lm


def _pdf(path: Path, text: str) -> Path:
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), text)
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def calls(monkeypatch):
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "https://test.cognitiveservices.azure.com")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "k")
    lm.clear_analyze_memo()
    seen: list[Path] = []

    def fake_analyze(pdf_path: Path):
        seen.append(pdf_path)
        return object(), {"n": len(seen)}, f"op-{len(seen)}"

    monkeypatch.setattr(lm, "_analyze_azure", fake_analyze)
    monkeypatch.setattr(
        lm, "build_layout_map_from_result", lambda result, doc: lm.LayoutMap(pages=[], boxes=[])
    )
    yield seen
    lm.clear_analyze_memo()


def test_same_file_is_analyzed_once(tmp_path: Path, calls) -> None:
    pdf = _pdf(tmp_path / "a.pdf", "alpha")
    first, client1, result1 = lm.analyze_layout_map(pdf)
    second, client2, result2 = lm.analyze_layout_map(pdf)
    assert len(calls) == 1
    assert result1 is result2 and client1 is client2
    assert first.operation_id == second.operation_id == "op-1"
    assert first is not second


def test_different_content_is_analyzed_again(tmp_path: Path, calls) -> None:
    lm.analyze_layout_map(_pdf(tmp_path / "a.pdf", "alpha"))
    lm.analyze_layout_map(_pdf(tmp_path / "b.pdf", "beta"))
    assert len(calls) == 2


def test_failed_analyze_is_not_kept(tmp_path: Path, calls, monkeypatch) -> None:
    pdf = _pdf(tmp_path / "a.pdf", "alpha")
    ok = lm._analyze_azure

    def boom(_path: Path):
        raise RuntimeError("azure_timeout")

    monkeypatch.setattr(lm, "_analyze_azure", boom)
    with pytest.raises(RuntimeError):
        lm.analyze_layout_map(pdf)
    monkeypatch.setattr(lm, "_analyze_azure", ok)
    lm.analyze_layout_map(pdf)
    assert len(calls) == 1


def test_kept_result_expires(tmp_path: Path, calls, monkeypatch) -> None:
    pdf = _pdf(tmp_path / "a.pdf", "alpha")
    lm.analyze_layout_map(pdf)
    monkeypatch.setattr(lm, "_ANALYZE_TTL_S", -1.0)
    lm.analyze_layout_map(pdf)
    assert len(calls) == 2


def test_only_a_few_results_are_kept(tmp_path: Path, calls) -> None:
    pdfs = [_pdf(tmp_path / f"{i}.pdf", f"paper {i}") for i in range(lm._ANALYZE_KEEP + 1)]
    for pdf in pdfs:
        lm.analyze_layout_map(pdf)
    lm.analyze_layout_map(pdfs[0])
    assert len(calls) == lm._ANALYZE_KEEP + 2
    assert len(lm._ANALYZE_MEMO) == lm._ANALYZE_KEEP
