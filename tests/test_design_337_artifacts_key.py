"""design/337 — module-global geometry must not cross between concurrent ingests.

`_last_artifacts` / `_last_census` are process-global. Cloud Run runs this service
at `--concurrency 16` and `_run_ingest_job` is a bare `asyncio.create_task`, so two
ingests share the process, and `extract_figures` runs in a worker thread. The
artifacts read sat ~500 lines and many awaits after the extract that produced
them, and the value is *persisted*, so a crossed read is a data defect, not just a
reporting one: paper A would store paper B's `layout_map` and `slot_plan`, and
every later re-render and figure edit for A would reason about B's geometry.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sentence_reading.pdf import extract_figures_v2 as v2
from sentence_reading.pdf.slot_plan import Slot, SlotPlan, slot_census


class _Box:
    def __init__(self, kind: str, bid: str) -> None:
        self.kind = kind
        self.id = bid
        self.used_by_slot = ""


class _Layout:
    def __init__(self) -> None:
        self.boxes: list[_Box] = []

    def to_dict(self) -> dict:
        return {"boxes": len(self.boxes)}

    def unused_boxes(self, kind: str) -> list[_Box]:
        return [b for b in self.boxes if b.kind == kind and not b.used_by_slot]


@pytest.fixture(autouse=True)
def _reset() -> None:
    v2._last_artifacts = None
    v2._last_census = None
    v2._last_key = None


def _set(path: str) -> None:
    plan = SlotPlan(slots=[Slot(key="fig:1", kind="fig", n=1, status="empty")])
    v2._set_artifacts(_Layout(), plan, Path(path))


def test_the_matching_document_gets_its_own_geometry() -> None:
    _set("/tmp/paper_a.pdf")
    assert v2.get_last_layout_artifacts(Path("/tmp/paper_a.pdf")) is not None
    assert v2.get_last_slot_census(Path("/tmp/paper_a.pdf")) is not None


def test_another_document_is_refused_rather_than_served() -> None:
    _set("/tmp/paper_a.pdf")
    assert v2.get_last_layout_artifacts(Path("/tmp/paper_b.pdf")) is None
    assert v2.get_last_slot_census(Path("/tmp/paper_b.pdf")) is None


def test_a_second_ingest_overwriting_is_caught() -> None:
    """The live race: A extracts, B extracts, then A reads."""
    _set("/tmp/paper_a.pdf")
    _set("/tmp/paper_b.pdf")
    assert v2.get_last_layout_artifacts(Path("/tmp/paper_a.pdf")) is None
    assert v2.get_last_layout_artifacts(Path("/tmp/paper_b.pdf")) is not None


def test_no_expectation_keeps_the_old_behaviour() -> None:
    _set("/tmp/paper_a.pdf")
    assert v2.get_last_layout_artifacts() is not None
    assert v2.get_last_slot_census() is not None


def test_a_cleared_key_refuses_everything() -> None:
    assert v2.get_last_layout_artifacts(Path("/tmp/paper_a.pdf")) is None


# ------------------------------------------------------------ pairing census


def test_census_reports_the_pairing_not_just_the_totals() -> None:
    """The defect the counters could not see: 33% of slots are caption-less images."""
    plan = SlotPlan(
        slots=[
            Slot(key="fig:1", kind="fig", n=1, status="partial", caption_box_id="c1"),
            Slot(
                key="fig:2",
                kind="fig",
                n=2,
                status="filled",
                caption_box_id="c2",
                body_box_id="b2",
            ),
            Slot(key="fig:3", kind="fig", n=3, status="partial", body_box_id="b3", unnumbered=True),
            Slot(key="fig:4", kind="fig", n=4, status="partial", body_box_id="b4", unnumbered=True),
        ]
    )
    census = slot_census(_Layout(), plan)
    assert census["caption_without_body_n"] == 1
    assert census["body_without_caption_n"] == 2
    assert census["unnumbered_n"] == 2
    # The old verdict fields still read green on exactly this input, which is why
    # the pairing needed its own counters.
    assert census["unused_body_n"] == 0
    assert census["slot_n"] >= census["body_n"]


def test_caption_text_alone_counts_as_a_caption() -> None:
    plan = SlotPlan(
        slots=[Slot(key="fig:1", kind="fig", n=1, status="partial", caption_text="Figure 1.")]
    )
    census = slot_census(_Layout(), plan)
    assert census["caption_without_body_n"] == 1
    assert census["body_without_caption_n"] == 0
