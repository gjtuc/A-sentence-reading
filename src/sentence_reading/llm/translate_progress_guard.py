"""design/283 — translate section pass / progress regress tracker (server)."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from typing import Any

_PHASE_HARMONIZE = "harmonize"
_PHASE_TRANSLATE = "translate"
_PHASE_DIGEST = "digest"
_PHASE_CAPTION = "caption"


def phase_token(raw: str) -> str:
    s = (raw or "").strip().lower()
    if "harmonize" in s or "재감수" in s:
        return _PHASE_HARMONIZE
    if "digest" in s or "요지" in s:
        return _PHASE_DIGEST
    if "caption" in s or "캡션" in s:
        return _PHASE_CAPTION
    if "translate" in s or "번역" in s:
        return _PHASE_TRANSLATE
    return "other"


def section_token(raw: str) -> str:
    s = (raw or "").strip().lower()
    s = s.replace(":", "_").replace("-", "_").replace(" ", "_")
    s = re.sub(r"[^a-z0-9_]", "", s)[:64]
    if not s or not re.match(r"^[a-z]", s):
        return "unknown"
    return s


@dataclass
class _Slot:
    pass_n: int = 0
    last_out_n: int = -1
    last_in_n: int = 0


@dataclass
class TranslatePassTracker:
    """Per-job section/phase progress; thread-safe."""

    _lock: threading.Lock = field(default_factory=threading.Lock)
    _slots: dict[str, _Slot] = field(default_factory=dict)

    def _key(self, job_id: str, section: str, phase: str) -> str:
        return f"{(job_id or '').strip()}|{section_token(section)}|{phase_token(phase)}"

    def note_section_enter(
        self,
        *,
        job_id: str,
        section: str,
        in_n: int,
        queue_i: int = 0,
        queue_n: int = 0,
    ) -> dict[str, Any]:
        """Return details for translate_section_enter (+ loop flags)."""
        sec = section_token(section)
        phase = _PHASE_TRANSLATE
        with self._lock:
            slot = self._slots.setdefault(self._key(job_id, sec, phase), _Slot())
            # New section enter for this job+section ⇒ new pass
            slot.pass_n += 1
            slot.last_out_n = -1
            slot.last_in_n = int(in_n)
            pass_n = slot.pass_n
        return {
            "section": sec,
            "phase": phase,
            "pass_n": pass_n,
            "in_n": int(in_n),
            "queue_i": int(queue_i),
            "queue_n": int(queue_n),
            "loop": 1 if pass_n >= 2 else 0,
        }

    def note_harmonize_start(
        self,
        *,
        job_id: str,
        section: str,
        in_n: int,
        worker_n: int = 0,
        residual: bool = False,
    ) -> dict[str, Any]:
        sec = section_token(section)
        # Residual arm is a normal second pool — own phase so it does not
        # look like a full 재감수 restart loop (design/283).
        phase = "harmonize_residual" if residual else _PHASE_HARMONIZE
        with self._lock:
            slot = self._slots.setdefault(self._key(job_id, sec, phase), _Slot())
            slot.pass_n += 1
            slot.last_out_n = -1
            slot.last_in_n = int(in_n)
            pass_n = slot.pass_n
        out = {
            "section": sec,
            "phase": phase,
            "pass_n": pass_n,
            "in_n": int(in_n),
            "worker_n": int(worker_n),
            "loop": 1 if (not residual and pass_n >= 2) else 0,
        }
        if residual:
            out["residual"] = 1
        return out

    def note_harmonize_tick(
        self,
        *,
        job_id: str,
        section: str,
        out_n: int,
        in_n: int,
        remaining: int = 0,
        residual: bool = False,
    ) -> tuple[dict[str, Any], bool]:
        """Returns (details, regress)."""
        sec = section_token(section)
        phase = "harmonize_residual" if residual else _PHASE_HARMONIZE
        regress = False
        prev = -1
        with self._lock:
            slot = self._slots.setdefault(self._key(job_id, sec, phase), _Slot())
            if slot.pass_n < 1:
                slot.pass_n = 1
            prev = slot.last_out_n
            cur = int(out_n)
            if prev >= 0 and cur < prev:
                regress = True
            # Drop from near-complete back to early
            if (
                prev >= 0
                and slot.last_in_n > 0
                and prev >= int(0.8 * slot.last_in_n)
                and cur <= int(0.2 * max(1, int(in_n)))
            ):
                regress = True
            slot.last_out_n = cur
            if int(in_n) > 0:
                slot.last_in_n = int(in_n)
            pass_n = slot.pass_n
        details = {
            "section": sec,
            "phase": phase,
            "pass_n": pass_n,
            "out_n": int(out_n),
            "in_n": int(in_n),
            "remaining": int(remaining),
            "prev_out_n": prev if prev >= 0 else -1,
            "regress": 1 if regress else 0,
        }
        if residual:
            details["residual"] = 1
        return details, regress

    def note_harmonize_end(
        self,
        *,
        job_id: str,
        section: str,
        out_n: int,
        in_n: int,
        residual: bool = False,
    ) -> dict[str, Any]:
        sec = section_token(section)
        phase = "harmonize_residual" if residual else _PHASE_HARMONIZE
        with self._lock:
            slot = self._slots.setdefault(self._key(job_id, sec, phase), _Slot())
            if slot.pass_n < 1:
                slot.pass_n = 1
            slot.last_out_n = int(out_n)
            if int(in_n) > 0:
                slot.last_in_n = int(in_n)
            pass_n = slot.pass_n
        out = {
            "section": sec,
            "phase": phase,
            "pass_n": pass_n,
            "out_n": int(out_n),
            "in_n": int(in_n),
        }
        if residual:
            out["residual"] = 1
        return out

    def clear_job(self, job_id: str) -> None:
        prefix = f"{(job_id or '').strip()}|"
        with self._lock:
            drop = [k for k in self._slots if k.startswith(prefix)]
            for k in drop:
                del self._slots[k]


# Process-wide default tracker (ingest worker).
TRANSLATE_PASS_TRACKER = TranslatePassTracker()
