"""design/151 — slot order finalize + Azure orphan merge removal."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz
import pytest

from sentence_reading.fig_refs import caption_key
from sentence_reading.models import Figure
from sentence_reading.pdf.extract import _finalize_figure_list, extract_figures


def _fig(caption: str, *, slot_key: str = "", page: int = 0, fid: str = "x") -> Figure:
    return Figure(
        id=fid,
        image_src="data:image/png;base64,AA==",
        caption=caption,
        page_index=page,
        slot_key=slot_key,
    )


def _empty_doc() -> fitz.Document:
    doc = fitz.open()
    doc.new_page()
    return doc


def test_finalize_preserves_slot_order_and_slot_key() -> None:
    raw = [
        _fig("Figure 1.", slot_key="fig:1", page=1),
        _fig("Figure 2.", slot_key="fig:2", page=2),
        _fig("Figure 3.", slot_key="fig:3", page=3),
        _fig("Figure 4.", slot_key="fig:4", page=4),
        _fig("Figure 5.", slot_key="fig:5", page=5),
        _fig("Figure 6.", slot_key="fig:6", page=6),
        _fig("Figure 7.", slot_key="fig:7", page=7),
        _fig("Table 1.", slot_key="table:1", page=3),
        _fig("Table 2.", slot_key="table:2", page=4),
        _fig("Table 3.", slot_key="table:3", page=5),
        _fig(
            "Figure S1 shows in situ diffraction patterns",
            page=4,
        ),
        _fig(
            "figure S7. of 62.1, 33.3 and 4.6%",
            page=6,
        ),
    ]
    doc = _empty_doc()
    try:
        out = _finalize_figure_list(doc, raw)
    finally:
        doc.close()

    assert len(out) == 10
    assert [f.slot_key for f in out] == [
        "fig:1",
        "fig:2",
        "fig:3",
        "fig:4",
        "fig:5",
        "fig:6",
        "fig:7",
        "table:1",
        "table:2",
        "table:3",
    ]
    assert out[7].caption.startswith("Table 1.")


def test_coti_like_carousel_mapping() -> None:
    """14 Azure slots + 2 PyMuPDF orphans → 14 carousel; #8 = Table 1."""
    raw = []
    for n in range(1, 8):
        raw.append(_fig(f"Figure {n}. Test", slot_key=f"fig:{n}", page=n))
    for n in range(1, 8):
        raw.append(_fig(f"Table {n}. Test", slot_key=f"table:{n}", page=n + 2))
    raw.append(
        _fig(
            "Figure S1 shows in situ diffraction patterns for the Co-P25 catalyst",
            page=4,
        )
    )
    raw.append(
        _fig(
            "figure S7. of 62.1, 33.3 and 4.6% respectively at the end of the reaction",
            page=6,
        )
    )

    doc = _empty_doc()
    try:
        out = _finalize_figure_list(doc, raw)
    finally:
        doc.close()

    assert len(out) == 14
    assert out[7].slot_key == "table:1"
    assert caption_key(out[7].caption) == "table:1"
    assert out[0].slot_key == "fig:1"
    assert out[6].slot_key == "fig:7"
    assert out[13].slot_key == "table:7"


def test_extract_figures_azure_skips_pymupdf_orphan_merge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = tmp_path / "t.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(pdf)
    doc.close()

    azure_fig = _fig("Fig. 1. Azure crop", slot_key="fig:1", page=0, fid="slot-0001")

    monkeypatch.setenv("ASR_AZURE_LAYOUT", "1")
    monkeypatch.setenv(
        "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT",
        "https://test.cognitiveservices.azure.com",
    )
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "k")

    with patch(
        "sentence_reading.pdf.extract_figures_v2.extract_figures_v2",
        return_value=[azure_fig],
    ) as mock_v2:
        with patch(
            "sentence_reading.pdf.extract._collect_pymupdf_figures",
        ) as mock_pymupdf:
            figs = extract_figures(pdf)

    mock_v2.assert_called_once()
    mock_pymupdf.assert_not_called()
    assert len(figs) == 1
    assert figs[0].slot_key == "fig:1"


def test_extract_figures_azure_empty_skips_pymupdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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

    with patch(
        "sentence_reading.pdf.extract_figures_v2.extract_figures_v2",
        return_value=[],
    ) as mock_v2:
        with patch(
            "sentence_reading.pdf.extract._collect_pymupdf_figures",
        ) as mock_pymupdf:
            figs = extract_figures(pdf)

    mock_v2.assert_called_once()
    mock_pymupdf.assert_not_called()
    assert figs == []


def test_finalize_legacy_path_still_sorts_pymupdf_only() -> None:
    raw = [
        _fig("Table 1. Results", page=2),
        _fig("Fig. 2. Second", page=3),
        _fig("Fig. 1. First", page=1),
    ]
    doc = _empty_doc()
    try:
        out = _finalize_figure_list(doc, raw)
    finally:
        doc.close()

    keys = [caption_key(f.caption) for f in out]
    assert keys == ["fig:1", "fig:2", "table:1"]
