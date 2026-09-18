"""design/255 — FastAPI domain routers (Phase 1+)."""

from sentence_reading.api.routes import access as access_routes
from sentence_reading.api.routes import auth as auth_routes
from sentence_reading.api.routes import status as status_routes
from sentence_reading.api.routes import tts as tts_routes

__all__ = ["access_routes", "auth_routes", "status_routes", "tts_routes"]
