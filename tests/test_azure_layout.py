"""design/147 — Azure Document Intelligence layout extract."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sentence_reading.fig_refs import caption_key
from sentence_reading.llm.env import azure_document_intelligence_available
from sentence_reading.models import Figure
from sentence_reading.pdf import azure_layout
from sentence_reading.pdf.extract import extract_figures


@pytest.fixture(autouse=True)
def _no_azure_in_unit_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_SKIP_ENV_FILE", "1")
    monkeypatch.setenv("ASR_AZURE_LAYOUT", "0")
    monkeypatch.delenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", raising=False)


def test_azure_layout_enabled_kill_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_AZURE_LAYOUT", "1")
    assert azure_layout.azure_layout_enabled() is True
    monkeypatch.setenv("ASR_AZURE_LAYOUT", "0")
    assert azure_layout.azure_layout_enabled() is False


def test_azure_available_requires_both(monkeypatch: pytest.MonkeyPatch) -> None:
    assert azure_document_intelligence_available() is False
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "https://x.cognitiveservices.azure.com")
    assert azure_document_intelligence_available() is False
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "secret")
    assert azure_document_intelligence_available() is True


def test_polygon_to_rect_inches_to_points() -> None:
    import fitz

    rect = azure_layout._polygon_to_rect([0.0, 0.0, 2.0, 0.0, 2.0, 1.0, 0.0, 1.0])
    assert rect is not None
    assert isinstance(rect, fitz.Rect)
    assert rect.width == pytest.approx(144.0)
    assert rect.height == pytest.approx(72.0)


def test_extract_figures_uses_azure_when_configured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import fitz

    pdf = tmp_path / "t.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello")
    doc.save(pdf)
    doc.close()

    azure_fig = Figure(
        id="fig-azure",
        image_src="data:image/png;base64,AA==",
        caption="Fig. 1. Azure crop",
        page_index=0,
    )

    monkeypatch.setenv("ASR_AZURE_LAYOUT", "1")
    monkeypatch.setenv(
        "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT",
        "https://test.cognitiveservices.azure.com",
    )
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "k")

    with patch(
        "sentence_reading.pdf.extract_figures_v2.extract_figures_v2",
        return_value=[azure_fig],
    ) as mock_azure:
        figs = extract_figures(pdf)
    mock_azure.assert_called_once()
    assert any(caption_key(f.caption) == "fig:1" for f in figs)


def test_extract_figures_falls_back_when_azure_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import fitz

    pdf = tmp_path / "t.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(pdf)
    doc.close()

    monkeypatch.setenv("ASR_AZURE_LAYOUT", "1")
    monkeypatch.setenv(
        "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT",
        "https://test.cognitiveservices.azure.com",
    )
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "k")

    with patch("sentence_reading.pdf.extract_figures_v2.extract_figures_v2", return_value=[]):
        figs = extract_figures(pdf)
    assert figs == []


def test_status_reports_azure_layout(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from sentence_reading.api.app import app
    from sentence_reading.llm.typography import PIPELINE_VERSION

    monkeypatch.setenv("ASR_AZURE_LAYOUT", "1")
    monkeypatch.delenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", raising=False)
    st = TestClient(app).get("/api/status").json()
    assert st["azure_layout"] is False
    assert st["azure_layout_enabled"] is True
    assert st["pipeline_version"] == PIPELINE_VERSION == "rich-v24"

    monkeypatch.setenv(
        "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT",
        "https://test.cognitiveservices.azure.com",
    )
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "k")
    st2 = TestClient(app).get("/api/status").json()
    assert st2["azure_layout"] is True


def test_extract_figures_azure_maps_figure_and_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fitz

    pdf = tmp_path / "paper.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 500), "Fig. 1. Test plot")
    page.insert_text((72, 170), "Table 1. Results")
    doc.save(pdf)
    doc.close()

    monkeypatch.setenv("ASR_AZURE_LAYOUT", "1")
    monkeypatch.setenv(
        "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT",
        "https://test.cognitiveservices.azure.com",
    )
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "k")

    mock_figure = MagicMock()
    mock_figure.id = "1.1"
    mock_figure.caption = MagicMock(content="Fig. 1. Test plot")
    mock_figure.bounding_regions = [
        MagicMock(page_number=1, polygon=[0.5, 0.5, 2.0, 0.5, 2.0, 2.0, 0.5, 2.0])
    ]

    mock_table = MagicMock()
    mock_table.bounding_regions = [
        MagicMock(page_number=1, polygon=[0.5, 3.0, 3.0, 3.0, 3.0, 4.5, 0.5, 4.5])
    ]

    mock_result = MagicMock()
    mock_result.model_id = "prebuilt-layout"
    mock_result.figures = [mock_figure]
    mock_result.tables = [mock_table]

    mock_poller = MagicMock()
    mock_poller.result.return_value = mock_result
    mock_poller.details = {"operation_id": "op-1"}

    mock_client = MagicMock()
    mock_client.begin_analyze_document.return_value = mock_poller
    mock_client.get_analyze_result_figure.return_value = b"\x89PNG\r\n"

    with patch(
        "azure.ai.documentintelligence.DocumentIntelligenceClient",
        return_value=mock_client,
    ):
        figs = azure_layout.extract_figures_azure(pdf)

    keys = {caption_key(f.caption) for f in figs}
    assert "fig:1" in keys
    assert "table:1" in keys
    mock_client.get_analyze_result_figure.assert_called_once()


def test_accept_azure_figure_caption_good_title() -> None:
    assert azure_layout._accept_azure_figure_caption("Fig. 1. Test plot") is True


def test_reject_azure_body_captions() -> None:
    assert not azure_layout._accept_azure_figure_caption(
        "Figure S1 shows in situ diffraction patterns for the Co-P25 catalyst"
    )
    assert not azure_layout._accept_azure_figure_caption(
        "figure S7. of 62.1, 33.3 and 4.6% respectively at the end of the reaction"
    )
    assert not azure_layout._accept_azure_figure_caption(
        "Fig. 8 shows another body-like false positive."
    )


def test_figure_caption_placeholder() -> None:
    assert azure_layout._figure_caption_placeholder(
        "figure S7. of 62.1%", 8
    ) == "figure S7 (p.9)"


def test_status_figure_caption_in_image(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from sentence_reading.api import app as app_mod

    st = TestClient(app_mod.app).get("/api/status").json()
    assert st["version"] == "0.3.83"
    assert st["figure_caption_in_image"] is True
    assert st["mobile_figure_caption_in_image"] is True

    monkeypatch.setenv("ASR_FIGURE_CAPTION_IN_IMAGE", "0")
    st2 = TestClient(app_mod.app).get("/api/status").json()
    assert st2["figure_caption_in_image"] is False
