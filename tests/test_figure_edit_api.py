"""design/151 — figure_edit API routes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentence_reading.api.app import app
from sentence_reading.cache import paper_cache as pc
from sentence_reading.pdf.layout_map import LayoutMap, save_layout_map
from sentence_reading.pdf.slot_plan import Slot, SlotPlan, save_slot_plan


@pytest.fixture
def cache_with_layout(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pc, "cache_root", lambda: tmp_path)
    monkeypatch.setattr(
        "sentence_reading.llm.access_gate.access_gate_enabled", lambda: False
    )
    monkeypatch.setattr(
        "sentence_reading.llm.auth_google.auth_enabled", lambda: False
    )
    cid = "abcd1234efgh"
    paper_dir = tmp_path / cid
    paper_dir.mkdir(parents=True)
    (paper_dir / "session.json").write_text(
        json.dumps({"title": "Test", "figures": [], "sentences": []}) + "\n",
        encoding="utf-8",
    )
    layout = LayoutMap(
        pages=[{"page_index": 0, "width_pt": 612, "height_pt": 792}],
        boxes=[
            {
                "id": "fb-0001",
                "page_index": 0,
                "kind": "figure_body",
                "rect": {"x0": 10, "y0": 10, "x1": 100, "y1": 100},
                "text": "",
                "azure_ref": "",
                "used_by_slot": "",
            }
        ],
    )
    # fix boxes as LayoutBox objects
    from sentence_reading.pdf.layout_map import LayoutBox

    layout = LayoutMap(
        pages=[{"page_index": 0, "width_pt": 612, "height_pt": 792}],
        boxes=[
            LayoutBox(
                id="fb-0001",
                page_index=0,
                kind="figure_body",
                rect={"x0": 10, "y0": 10, "x1": 100, "y1": 100},
            )
        ],
    )
    save_layout_map(paper_dir, layout)
    save_slot_plan(
        paper_dir,
        SlotPlan(slots=[Slot(key="fig:1", kind="fig", n=1, status="empty")]),
    )
    return cid


def test_get_layout_map_and_slot_plan(cache_with_layout: str) -> None:
    client = TestClient(app)
    cid = cache_with_layout
    r1 = client.get(f"/api/cache/papers/{cid}/layout_map")
    assert r1.status_code == 200
    assert r1.json()["ok"] is True
    assert "boxes" in r1.json()["layout_map"]
    r2 = client.get(f"/api/cache/papers/{cid}/slot_plan")
    assert r2.status_code == 200
    assert r2.json()["slot_plan"]["slots"][0]["key"] == "fig:1"


def test_assign_slot_user_confirmed(cache_with_layout: str) -> None:
    client = TestClient(app)
    cid = cache_with_layout
    r = client.post(
        f"/api/cache/papers/{cid}/slots/fig:1/assign",
        json={"body_box_id": "fb-0001"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    slot = body["slot_plan"]["slots"][0]
    assert slot["status"] == "user_confirmed"
    assert slot["body_box_id"] == "fb-0001"
