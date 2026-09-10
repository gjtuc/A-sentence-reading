"""design/209 kill — practice cycle evidence permanently off."""

from sentence_reading.llm.practice_cycle_evidence import practice_cycle_evidence_enabled
from sentence_reading.llm.evidence_kinds import ALLOWED_KINDS


def test_practice_cycle_evidence_hard_off(monkeypatch):
    monkeypatch.setenv("ASR_PRACTICE_CYCLE_EVIDENCE", "1")
    assert practice_cycle_evidence_enabled() is False


def test_kinds_removed_from_allowlist():
    assert "practice_cycle_wide" not in ALLOWED_KINDS
    assert "practice_evidence_flush" not in ALLOWED_KINDS
