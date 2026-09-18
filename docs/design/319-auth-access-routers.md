# 319 — Auth and access route tables (255 Phase 2)

**Version:** 0.3.314 · Status: **locked** (ops; no product bump)  
Amends [255](255-architecture-refactoring-roadmap.md)

## Why

`app.py` still owned `/api/auth/*` and `/api/access/*` on the FastAPI `app`
object. Phase 1 already moved status/TTS. Auth and access are the next
canary: path tables leave `app`, helpers leave `app`, handler bodies stay
until OAuth helpers can move without a circular import.

## Locked

1. `api/deps.py` owns `request_user`, `is_admin_user`, `paid_access_denied`.
   `app.py` imports them as `_request_user` / `_is_admin_user` /
   `_paid_access_denied`.
2. `routes/auth.py` and `routes/access.py` own the route tables.
   `app.py` decorates handlers with those routers, then `include_router`
   after the last handler (logout). Include must be after decorate.
3. Version string stays in `app.py`.
4. Handler bodies stay in `app.py` this chip.
5. Locks/`_SESSIONS` stay in `app.py` (context.py is a later chip).

## Not this chip

- Moving OAuth/email handler bodies
- `library_controller.dart` facade
- Version bump / deploy
