"""design/213 — skill evidence kill + kinds present."""

from sentence_reading.llm.evidence_kinds import ALLOWED_KINDS
from sentence_reading.llm.practice_skill_evidence import (
    practice_skill_evidence_enabled,
)


def test_skill_evidence_kinds_allowlisted():
    for k in (
        "practice_skill_spoken",
        "practice_skill_stt",
        "practice_skill_scored",
        "practice_skill_unscored",
        "practice_skill_adapt",
        "practice_skill_flush",
    ):
        assert k in ALLOWED_KINDS


def test_skill_evidence_kill(monkeypatch):
    monkeypatch.setenv("ASR_PRACTICE_SKILL", "1")
    monkeypatch.delenv("ASR_PRACTICE_SKILL_EVIDENCE", raising=False)
    assert practice_skill_evidence_enabled() is True
    monkeypatch.setenv("ASR_PRACTICE_SKILL_EVIDENCE", "0")
    assert practice_skill_evidence_enabled() is False
