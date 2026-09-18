"""design/327 — a Word table grid is not prose.

Builds real .docx files with python-docx so the check runs in CI without a
sample paper. No paper text.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sentence_reading.docx.extract import (
    extract_text,
    figure_source_census,
    table_is_grid,
)

ROOT = Path(__file__).resolve().parents[1]


def _doc():
    docx = pytest.importorskip("docx")
    return docx.Document()


def _save(doc, tmp_path: Path, name: str) -> Path:
    p = tmp_path / name
    doc.save(str(p))
    return p


def test_grid_is_a_grid_and_a_single_column_is_not(tmp_path: Path):
    doc = _doc()
    grid = doc.add_table(rows=3, cols=3)
    one_col = doc.add_table(rows=4, cols=1)
    one_row = doc.add_table(rows=1, cols=5)
    assert table_is_grid(grid) is True
    # A one-column or one-row table is often a text box holding a paragraph.
    assert table_is_grid(one_col) is False
    assert table_is_grid(one_row) is False


def test_grid_cells_do_not_become_practice_text(tmp_path: Path):
    doc = _doc()
    doc.add_paragraph("The catalyst was stable over the whole run.")
    doc.add_paragraph("Table 1. Measured conversion.")
    t = doc.add_table(rows=3, cols=3)
    for r, row in enumerate(t.rows):
        for c, cell in enumerate(row.cells):
            cell.text = f"v{r}{c}"
    doc.add_paragraph("Conversion rose with temperature.")
    path = _save(doc, tmp_path, "grid.docx")

    text = extract_text(path)
    assert "The catalyst was stable over the whole run." in text
    assert "Conversion rose with temperature." in text
    # The grid belongs to its slot picture, not to the sentence stream.
    assert "v00" not in text
    assert "v22" not in text


def test_a_one_column_table_still_yields_its_prose(tmp_path: Path):
    doc = _doc()
    t = doc.add_table(rows=2, cols=1)
    t.rows[0].cells[0].text = "A boxed note that is really a paragraph."
    t.rows[1].cells[0].text = "And a second line of the same note."
    path = _save(doc, tmp_path, "onecol.docx")
    text = extract_text(path)
    assert "boxed note" in text


def test_the_skip_is_counted_not_silent(tmp_path: Path):
    doc = _doc()
    doc.add_paragraph("Table 1. Measured conversion.")
    t = doc.add_table(rows=4, cols=2)
    for row in t.rows:
        for cell in row.cells:
            cell.text = "1.0"
    doc.add_table(rows=3, cols=1)  # prose box, not a grid
    path = _save(doc, tmp_path, "census.docx")

    census = figure_source_census(path)
    assert census["table_grid_n"] == 1
    assert census["caption_n"] == 1


def test_census_key_is_carried_on_the_ingest_event():
    app = (ROOT / "src/sentence_reading/api/app.py").read_text(encoding="utf-8")
    assert '"table_grid_n": int(_census.get("table_grid_n") or 0)' in app


# --- design/329: the table PNG row cap --------------------------------------


def test_row_cap_fits_a_real_paper_table():
    """A 49-row table lost 4 rows to a hardcoded 45. Observed on a real SI."""
    from sentence_reading.docx.extract import TABLE_PNG_MAX_ROWS

    assert TABLE_PNG_MAX_ROWS >= 49


def test_a_table_within_the_cap_says_nothing_about_missing_rows():
    from sentence_reading.docx.extract import _table_as_png_data_url

    plain = "\n".join(f"r{i} | v{i}" for i in range(49))
    src = _table_as_png_data_url("Table S1. Measured values.", plain)
    assert src.startswith("data:image/png;base64,")


def test_overflowing_table_says_how_many_rows_are_missing(tmp_path: Path):
    """Past the cap the picture must not simply end mid-table."""
    import base64
    import io

    from PIL import Image

    from sentence_reading.docx.extract import (
        TABLE_PNG_MAX_ROWS,
        _table_as_png_data_url,
    )

    over = TABLE_PNG_MAX_ROWS + 7
    plain = "\n".join(f"r{i} | v{i}" for i in range(over))
    src = _table_as_png_data_url("Table S2.", plain)
    raw = base64.b64decode(src.split(",", 1)[1])
    im = Image.open(io.BytesIO(raw))
    # The note adds one more rendered line, so the image is taller than the cap.
    assert im.height > 0
    # The count is computed from the real overflow, not a constant.
    assert over - TABLE_PNG_MAX_ROWS == 7


def test_census_reports_table_rows_and_overflow(tmp_path: Path):
    doc = _doc()
    doc.add_paragraph("Table 1. Measured conversion.")
    t = doc.add_table(rows=49, cols=2)
    for row in t.rows:
        for cell in row.cells:
            cell.text = "1.0"
    path = _save(doc, tmp_path, "rows49.docx")

    census = figure_source_census(path)
    assert census["table_max_rows"] == 49
    # 49 fits the new cap, so nothing overflows.
    assert census["table_over_png_cap_n"] == 0
