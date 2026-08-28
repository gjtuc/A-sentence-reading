"""
design/151 — figure layout overlay API (layout_map, slot_plan, assign, render).
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from sentence_reading.cache import paper_cache
from sentence_reading.cache.paper_cache import (
    get_source_path,
    load_cached_session,
)
from sentence_reading.pdf.extract_figures_v2 import render_slot_figure
from sentence_reading.pdf.layout_map import LayoutMap, load_layout_map, save_layout_map
from sentence_reading.pdf.slot_plan import (
    SlotPlan,
    assign_body_to_slot,
    assign_caption_to_slot,
    load_slot_plan,
    refresh_slot_statuses,
    save_slot_plan,
)

_CACHE_ID_RE = re.compile(r"^[a-zA-Z0-9]{8,32}$")


def _bad_id() -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"ok": False, "error": "bad_cache_id", "message": "잘못된 보관 id입니다."},
    )


def _not_found() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "ok": False,
            "error": "cache_not_found",
            "message": "보관된 논문을 찾을 수 없습니다.",
        },
    )


def _paper_dir(cache_id: str) -> Path | None:
    cid = (cache_id or "").strip()
    if not _CACHE_ID_RE.match(cid):
        return None
    return paper_cache.cache_root() / cid


def get_layout_map_response(cache_id: str) -> JSONResponse:
    paper_dir = _paper_dir(cache_id)
    if paper_dir is None:
        return _bad_id()
    layout = load_layout_map(paper_dir)
    if layout is None:
        return JSONResponse(
            status_code=404,
            content={
                "ok": False,
                "error": "layout_map_missing",
                "message": "레이아웃 맵이 없습니다. PDF를 재분석해 주세요.",
            },
        )
    return JSONResponse({"ok": True, "layout_map": layout.to_dict()})


def get_slot_plan_response(cache_id: str) -> JSONResponse:
    paper_dir = _paper_dir(cache_id)
    if paper_dir is None:
        return _bad_id()
    plan = load_slot_plan(paper_dir)
    if plan is None:
        return JSONResponse(
            status_code=404,
            content={
                "ok": False,
                "error": "slot_plan_missing",
                "message": "슬롯 계획이 없습니다. PDF를 재분석해 주세요.",
            },
        )
    return JSONResponse({"ok": True, "slot_plan": plan.to_dict()})


def post_slot_assign(cache_id: str, slot_key: str, body: dict[str, Any]) -> JSONResponse:
    paper_dir = _paper_dir(cache_id)
    if paper_dir is None:
        return _bad_id()
    layout = load_layout_map(paper_dir)
    plan = load_slot_plan(paper_dir)
    if layout is None or plan is None:
        return _not_found()
    slot = plan.slot_by_key(slot_key)
    if slot is None:
        return JSONResponse(
            status_code=404,
            content={"ok": False, "error": "slot_not_found", "message": "슬롯을 찾을 수 없습니다."},
        )
    body_box_id = str(body.get("body_box_id") or "").strip()
    caption_box_id = str(body.get("caption_box_id") or "").strip()
    if body_box_id:
        assign_body_to_slot(plan, layout, slot.key, body_box_id)
    if caption_box_id:
        cap_text = str(body.get("caption_text") or "").strip()
        assign_caption_to_slot(plan, layout, slot.key, caption_box_id, cap_text)
    slot.status = "user_confirmed"
    refresh_slot_statuses(plan)
    save_layout_map(paper_dir, layout)
    save_slot_plan(paper_dir, plan)
    return JSONResponse({"ok": True, "slot_plan": plan.to_dict()})


def _write_figure_png(paper_dir: Path, fig_id: str, png: bytes) -> str | None:
    fig_dir = paper_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    fname = re.sub(r"[^\w.\-]+", "_", f"{fig_id}.png")
    path = fig_dir / fname
    try:
        path.write_bytes(png)
    except OSError:
        return None
    return f"figures/{fname}"


def _decode_figure_png(image_src: str) -> bytes | None:
    raw = (image_src or "").strip()
    if raw.startswith("data:image"):
        try:
            b64 = raw.split(",", 1)[1]
            return base64.b64decode(b64)
        except (IndexError, ValueError):
            return None
    return None


def post_slot_render(cache_id: str, slot_key: str) -> JSONResponse:
    paper_dir = _paper_dir(cache_id)
    if paper_dir is None:
        return _bad_id()
    layout = load_layout_map(paper_dir)
    plan = load_slot_plan(paper_dir)
    if layout is None or plan is None:
        return _not_found()
    slot = plan.slot_by_key(slot_key)
    if slot is None:
        return JSONResponse(
            status_code=404,
            content={"ok": False, "error": "slot_not_found", "message": "슬롯을 찾을 수 없습니다."},
        )
    src = get_source_path(cache_id)
    if src is None or not src.is_file():
        return JSONResponse(
            status_code=404,
            content={
                "ok": False,
                "error": "source_missing",
                "message": "원본 PDF가 없어 렌더할 수 없습니다.",
            },
        )
    fig = render_slot_figure(src, layout, plan, slot.key)
    if fig is None:
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "render_failed", "message": "슬롯 렌더 실패"},
        )
    png = _decode_figure_png(fig.image_src)
    if not png:
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "render_failed", "message": "PNG 생성 실패"},
        )
    rel = _write_figure_png(paper_dir, fig.id, png)
    if rel is None:
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "write_failed", "message": "PNG 저장 실패"},
        )

    loaded = load_cached_session(cache_id, load_images=False)
    if loaded is not None:
        session, _info = loaded
        updated = False
        for i, f in enumerate(session.figures):
            if (f.slot_key or "").lower() == slot.key.lower():
                session.figures[i] = fig
                updated = True
                break
        if updated:
            sess_path = paper_dir / "session.json"
            try:
                meta = json.loads(sess_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                meta = {}
            if isinstance(meta, dict):
                figs = meta.get("figures") or []
                for row in figs:
                    if not isinstance(row, dict):
                        continue
                    if str(row.get("slot_key") or "").lower() == slot.key.lower():
                        row["caption"] = fig.caption
                        row["file"] = rel
                        row["page_index"] = fig.page_index
                        break
                meta["figures"] = figs
                sess_path.write_text(
                    json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
    try:
        from sentence_reading.llm.papers_gcs import upload_paper_cache

        upload_paper_cache(cache_id)
    except Exception:  # noqa: BLE001
        pass
    return JSONResponse(
        {
            "ok": True,
            "figure": {
                "id": fig.id,
                "caption": fig.caption,
                "page_index": fig.page_index,
                "slot_key": fig.slot_key,
                "file": rel,
            },
        }
    )


def register_figure_edit_routes(app, *, paid_access_denied) -> None:
    """Mount figure_edit routes on FastAPI app."""

    @app.get("/api/cache/papers/{cache_id}/layout_map")
    def cache_layout_map(request: Request, cache_id: str) -> JSONResponse:
        denied = paid_access_denied(request)
        if denied is not None:
            return denied
        return get_layout_map_response(cache_id)

    @app.get("/api/cache/papers/{cache_id}/slot_plan")
    def cache_slot_plan(request: Request, cache_id: str) -> JSONResponse:
        denied = paid_access_denied(request)
        if denied is not None:
            return denied
        return get_slot_plan_response(cache_id)

    @app.post("/api/cache/papers/{cache_id}/slots/{slot_key}/assign")
    async def cache_slot_assign(
        request: Request, cache_id: str, slot_key: str
    ) -> JSONResponse:
        denied = paid_access_denied(request)
        if denied is not None:
            return denied
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        if not isinstance(body, dict):
            body = {}
        return post_slot_assign(cache_id, slot_key, body)

    @app.post("/api/cache/papers/{cache_id}/slots/{slot_key}/render")
    def cache_slot_render(request: Request, cache_id: str, slot_key: str) -> JSONResponse:
        denied = paid_access_denied(request)
        if denied is not None:
            return denied
        return post_slot_render(cache_id, slot_key)
