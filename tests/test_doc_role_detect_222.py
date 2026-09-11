# -*- coding: utf-8 -*-
"""design/222 — doc_role detect densify + pairing gap + list content_hash."""
from __future__ import annotations

from pathlib import Path

from sentence_reading.cache.supplementary_library import (
    apply_pairing_pass,
    list_entries_for_api,
)
from sentence_reading.llm.evidence_kinds import ALLOWED_KINDS
from sentence_reading.pdf.supplementary_detect import (
    detect_doc_role,
    detect_doc_role_detailed,
)

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"
DESIGN = ROOT / "docs" / "design" / "222-doc-role-detect-disk-honesty.md"

_KINDS = (
    "doc_role_detect_start",
    "doc_role_detect_done",
    "doc_role_redetect_after_vision",
    "doc_role_pairing_gap",
)


def test_design_222_doc() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    assert "doc_role_detect_done" in text
    assert "post_vision" in text or "post-vision" in text.lower() or "vision" in text
    assert "PaperDiskIndexEntry" in text or "docRole" in text
    assert "ZWSP" in text or "format" in text.lower()


def test_kinds_allowlisted() -> None:
    dart = (MOBILE / "lib" / "services" / "evidence_kinds.dart").read_text(
        encoding="utf-8"
    )
    for k in _KINDS:
        assert k in ALLOWED_KINDS
        assert f"'{k}'" in dart


def test_zwsp_and_bom_still_si() -> None:
    body = "Supporting Information\nOptimizing the Ni/Cu Ratio for the Methane Dry Reforming\n"
    assert detect_doc_role("\ufeff\u200b" + body) == "supplementary"
    det = detect_doc_role_detailed("\u200b" + body)
    assert det.role == "supplementary"
    assert det.stripped_format is True
    assert det.reason == "head_marker"


def test_an1c_style_head_and_filename_secondary() -> None:
    head = (
        "Supporting Information Optimizing the Ni/Cu Ratio in Ni-Cu "
        "Nanoparticle Catalysts for the Methane Dry Reforming\n"
    )
    assert detect_doc_role(head, filename="an1c00673_si_001.pdf") == "supplementary"
    # No journal phrase, but SI filename + S-1 label
    weak = "S-1\n\nFig. S1 XRD of catalysts\nTable S1 BET areas\n"
    det = detect_doc_role_detailed(weak, filename="an1c00673_si_001.pdf")
    assert det.role == "supplementary"
    assert det.reason == "filename_si_and_page_label"


def test_main_midline_supporting_stays_main() -> None:
    mid = (
        "Abstract. Methods are described. Supporting Information is available "
        "online at ACS.\nResults follow.\n"
    )
    assert detect_doc_role(mid, filename="paper.pdf") == "main"


def test_pairing_gap_both_main_same_key() -> None:
    a = {
        "id": "aaa111111111",
        "title": "Optimizing the Ni/Cu Ratio for the Methane Dry Reforming catalysts study",
        "source": "pdf",
        "doc_role": "main",
        "updated_at": "2026-09-11T03:30:00+00:00",
        "sentence_count": 8,
        "figure_count": 6,
    }
    b = {
        "id": "bbb222222222",
        "title": "Optimizing the Ni/Cu Ratio for Methane Dry Reforming catalysts study",
        "source": "pdf",
        "doc_role": "main",
        "updated_at": "2026-09-11T03:39:00+00:00",
        "sentence_count": 234,
        "figure_count": 12,
    }
    rows = [a, b]
    apply_pairing_pass(rows)
    assert not a.get("paired_cache_id")
    assert not b.get("paired_cache_id")


def test_list_entries_exposes_content_hash() -> None:
    rows = list_entries_for_api(
        [
            {
                "id": "ccc333333333",
                "title": "Some Long Enough Paper Title For Library Row",
                "source": "pdf",
                "doc_role": "main",
                "content_hash": "a" * 64,
                "sentence_count": 10,
                "figure_count": 1,
            }
        ]
    )
    assert rows[0]["content_hash"] == "a" * 64


def test_mobile_disk_role_surface() -> None:
    disk = (MOBILE / "lib" / "services" / "paper_disk_store.dart").read_text(
        encoding="utf-8"
    )
    assert "docRole" in disk
    assert "force 메인" in disk or "persisted doc_role" in disk or "_tagForRole" in disk
    assert "doc_role" in disk
    app = (MOBILE / "lib" / "state" / "library_controller.dart").read_text(
        encoding="utf-8"
    )
    assert "docRole: e.docRole" in app
    assert "detect_doc_role_detailed" not in app  # server-only


def test_app_post_vision_redetect() -> None:
    app = (ROOT / "src" / "sentence_reading" / "api" / "app.py").read_text(
        encoding="utf-8"
    )
    assert "doc_role_redetect_after_vision" in app
    assert "post_vision" in app
    assert "detect_doc_role_detailed" in app
