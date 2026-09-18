"""design/255 Phase 2 — auth route table.

Handlers stay in app.py and are decorated with this router so the path
list is not on FastAPI `app` itself.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["auth"])
