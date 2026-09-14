"""design/255 Phase 1 — /api/status canary router (handler bound from app.py).

Version string and payload builders stay in app.py (design/255 invariant).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(tags=["status"])

_StatusHandler = Callable[[Request], dict[str, Any]]
_status_handler: _StatusHandler | None = None


def bind(*, status_handler: _StatusHandler) -> None:
    """Wire the app.py status payload builder once at startup."""
    global _status_handler
    _status_handler = status_handler


@router.get("/api/status")
def status(request: Request) -> dict[str, Any]:
    if _status_handler is None:
        raise RuntimeError("status router not bound")
    return _status_handler(request)
