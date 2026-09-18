"""design/255 Phase 2 — access-gate route table.

Handlers stay in app.py and are decorated with this router.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["access"])
