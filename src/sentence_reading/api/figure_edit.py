"""
design/151 — figure layout overlay API (layout_map, slot_plan, assign, render).
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from sentence_reading.cache import paper_cache
from sentence_reading.cache.paper_cache import (
    get_source_path,
    load_cached_session,
)
from sentence_reading.pdf.extract import render_page_png
from sentence_reading.pdf.extract_figures_v2 import render_slot_figure
from sentence_reading.pdf.layout_map import LayoutMap, load_layout_map, save_layout_map
from sentence_reading.pdf.slot_plan import (
    SlotPlan,
    assign_body_boxes_to_slot,
    assign_body_to_slot,
    assign_caption_boxes_to_slot,
    assign_caption_to_slot,
    load_slot_plan,
    refresh_slot_statuses,
    save_slot_plan,
)

_CACHE_ID_RE = re.compile(r"^[a-zA-Z0-9]{8,32}$")
_PAGE_PREVIEW_DIR = "page_previews"


def _source_missing() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "ok": False,
            "error": "source_missing",
            "message": "원본 PDF가 없습니다.",
        },
    )


def _resolve_source_path(cache_id: str) -> Path | None:
    src = get_source_path(cache_id)
    if src is not None and src.is_file():
        return src
    try:
        from sentence_reading.llm.papers_gcs import download_paper_cache

        download_paper_cache(cache_id, include_figures=False, include_source=True)
    except Exception:  # noqa: BLE001
        pass
    src = get_source_path(cache_id)
    if src is not None and src.is_file():
        return src
    return None


def _source_meta(src: Path) -> tuple[bytes, str, str]:
    from sentence_reading.llm.papers_gcs import PAPER_SOURCE_MAX_BYTES

    raw = src.read_bytes()
    if len(raw) > PAPER_SOURCE_MAX_BYTES:
        raise ValueError("source_too_large")
    digest = hashlib.sha256(raw).hexdigest()
    name = src.name
    if name.lower().endswith(".pdf"):
        ctype = "application/pdf"
    else:
        ctype = (
            "application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.document"
        )
    return raw, digest, ctype


def head_source_response(cache_id: str) -> Response:
    paper_dir = _paper_dir(cache_id)
    if paper_dir is None:
        return _bad_id()
    if not paper_dir.is_dir():
        return _not_found()
    src = _resolve_source_path(cache_id)
    if src is None:
        return _source_missing()
    try:
        raw, digest, _ctype = _source_meta(src)
    except ValueError:
        return JSONResponse(
            status_code=413,
            content={
                "ok": False,
                "error": "source_too_large",
                "message": "원본이 너무 큽니다.",
            },
        )
    except OSError:
        return _source_missing()
    return Response(
        status_code=200,
        headers={
            "Content-Length": str(len(raw)),
            "X-Content-Hash": digest,
            "X-Source-Filename": src.name,
        },
    )


def get_source_response(cache_id: str) -> Response:
    paper_dir = _paper_dir(cache_id)
    if paper_dir is None:
        return _bad_id()
    if not paper_dir.is_dir():
        return _not_found()
    src = _resolve_source_path(cache_id)
    if src is None:
        return _source_missing()
    try:
        raw, digest, ctype = _source_meta(src)
    except ValueError:
        return JSONResponse(
            status_code=413,
            content={
                "ok": False,
                "error": "source_too_large",
                "message": "원본이 너무 큽니다.",
            },
        )
    except OSError:
        return _source_missing()
    return Response(
        content=raw,
        media_type=ctype,
        headers={
            "Content-Length": str(len(raw)),
            "X-Content-Hash": digest,
            "Content-Disposition": f'attachment; filename="{src.name}"',
        },
    )


def get_page_preview_response(cache_id: str, page_index: int) -> Response:
    paper_dir = _paper_dir(cache_id)
    if paper_dir is None:
        return _bad_id()
    if not paper_dir.is_dir():
        return _not_found()
    if page_index < 0:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": "bad_page_index",
                "message": "page_index must be >= 0",
            },
        )
    preview_dir = paper_dir / _PAGE_PREVIEW_DIR
    preview_path = preview_dir / f"p{page_index}.png"
    if preview_path.is_file():
        try:
            cached = preview_path.read_bytes()
            if cached:
                return Response(content=cached, media_type="image/png")
        except OSError:
            pass
    src = _resolve_source_path(cache_id)
    if src is None:
        return _source_missing()
    try:
        png = render_page_png(src, page_index, dpi=120.0, max_side_px=1400)
    except (ValueError, IndexError, OSError, RuntimeError):
        return JSONResponse(
            status_code=404,
            content={
                "ok": False,
                "error": "page_not_found",
                "message": "페이지를 렌더할 수 없습니다.",
            },
        )
    try:
        preview_dir.mkdir(parents=True, exist_ok=True)
        preview_path.write_bytes(png)
    except OSError:
        pass
    return Response(content=png, media_type="image/png")


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
    body_box_ids = [
        str(x).strip()
        for x in (body.get("body_box_ids") or [])
        if str(x).strip()
    ]
    caption_box_ids = [
        str(x).strip()
        for x in (body.get("caption_box_ids") or [])
        if str(x).strip()
    ]
    if body_box_ids:
        assign_body_boxes_to_slot(plan, layout, slot.key, body_box_ids)
    elif body_box_id:
        assign_body_to_slot(plan, layout, slot.key, body_box_id)
    if caption_box_ids:
        cap_text = str(body.get("caption_text") or "").strip()
        assign_caption_boxes_to_slot(
            plan, layout, slot.key, caption_box_ids, cap_text
        )
    elif caption_box_id:
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


async def post_figure_edit_commit(cache_id: str, request: Request) -> JSONResponse:
    """design/163 — mobile local edit commit: manifest + slot PNGs."""
    paper_dir = _paper_dir(cache_id)
    if paper_dir is None:
        return _bad_id()
    if not paper_dir.is_dir():
        return _not_found()
    try:
        form = await request.form()
    except Exception:  # noqa: BLE001
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "bad_form", "message": "multipart 필요"},
        )
    manifest_raw = form.get("manifest")
    if not manifest_raw:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "manifest_missing", "message": "manifest 필요"},
        )
    try:
        manifest = json.loads(str(manifest_raw))
    except (TypeError, json.JSONDecodeError):
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "bad_manifest", "message": "manifest JSON 오류"},
        )
    if not isinstance(manifest, dict):
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "bad_manifest", "message": "manifest 형식 오류"},
        )

    layout_data = manifest.get("layout_map")
    plan_data = manifest.get("slot_plan")
    if isinstance(layout_data, dict):
        save_layout_map(paper_dir, LayoutMap.from_dict(layout_data))
    if isinstance(plan_data, dict):
        save_slot_plan(paper_dir, SlotPlan.from_dict(plan_data))

    sess_path = paper_dir / "session.json"
    meta: dict[str, Any] = {}
    if sess_path.is_file():
        try:
            loaded = json.loads(sess_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                meta = loaded
        except (OSError, json.JSONDecodeError):
            meta = {}
    fig_rows = meta.get("figures") or []
    if not isinstance(fig_rows, list):
        fig_rows = []

    updated_slots: list[str] = []
    for row in manifest.get("figures") or []:
        if not isinstance(row, dict):
            continue
        slot_key = str(row.get("slot_key") or "").strip()
        file_field = str(row.get("file_field") or "").strip()
        if not slot_key or not file_field:
            continue
        upload = form.get(file_field)
        if upload is None or not hasattr(upload, "read"):
            continue
        try:
            png = await upload.read()
        except Exception:  # noqa: BLE001
            continue
        if not png:
            continue
        fig_id = re.sub(r"[^\w.\-]+", "_", slot_key)
        rel = _write_figure_png(paper_dir, fig_id, png)
        if rel is None:
            continue
        caption = str(row.get("caption") or "")
        page_index = row.get("page_index")
        found = False
        for fig in fig_rows:
            if not isinstance(fig, dict):
                continue
            if str(fig.get("slot_key") or "").lower() == slot_key.lower():
                fig["caption"] = caption
                fig["file"] = rel
                if page_index is not None:
                    fig["page_index"] = page_index
                found = True
                break
        if not found:
            fig_rows.append(
                {
                    "id": fig_id,
                    "slot_key": slot_key,
                    "caption": caption,
                    "file": rel,
                    "page_index": page_index,
                }
            )
        updated_slots.append(slot_key)

    meta["figures"] = fig_rows
    try:
        sess_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "write_failed", "message": "session 저장 실패"},
        )

    try:
        from sentence_reading.llm.papers_gcs import upload_paper_cache

        upload_paper_cache(cache_id)
    except Exception:  # noqa: BLE001
        pass
    return JSONResponse({"ok": True, "updated_slots": updated_slots})


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

    @app.head("/api/cache/papers/{cache_id}/source")
    def cache_source_head(request: Request, cache_id: str) -> Response:
        denied = paid_access_denied(request)
        if denied is not None:
            return denied
        return head_source_response(cache_id)

    @app.get("/api/cache/papers/{cache_id}/source")
    def cache_source_get(request: Request, cache_id: str) -> Response:
        denied = paid_access_denied(request)
        if denied is not None:
            return denied
        return get_source_response(cache_id)

    @app.get("/api/cache/papers/{cache_id}/page_preview")
    def cache_page_preview(
        request: Request, cache_id: str, page_index: int = 0
    ) -> Response:
        denied = paid_access_denied(request)
        if denied is not None:
            return denied
        return get_page_preview_response(cache_id, page_index)

    @app.post("/api/cache/papers/{cache_id}/figure_edit/commit")
    async def cache_figure_edit_commit(
        request: Request, cache_id: str
    ) -> JSONResponse:
        denied = paid_access_denied(request)
        if denied is not None:
            return denied
        return await post_figure_edit_commit(cache_id, request)
