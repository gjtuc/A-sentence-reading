"""
무엇을: 로컬 HTTP — 정적 UI + status/mock/ingest(+Gemini debone, 제목 캐시, 진행률 폴링).
왜: 브라우저에서 Immersive식 문장 패널을 바로 검증한다.
다음에: 세션 LRU·caption 보강.
"""

from __future__ import annotations

import asyncio
import tempfile
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from sentence_reading.cache.paper_cache import (
    delete_cached_paper,
    find_cached_by_text,
    list_cached_papers,
    load_cached_session,
    save_paper_session,
)
from sentence_reading.docx import extract as docx_extract
from sentence_reading.llm.debone import DeboneResult, debone_sentences
from sentence_reading.llm.env import gemini_available, load_asr_env
from sentence_reading.models import PaperSession, build_mock_session
from sentence_reading.pdf import extract as pdf_extract
from sentence_reading.pdf.sentences import split_into_sentences

# WHY: static은 패키지 옆 — setuptools package-data와 개발 모드 모두에서 찾기 쉽게.
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

_MAX_UPLOAD_BYTES = 50 * 1024 * 1024
_SESSIONS: dict[str, PaperSession] = {}
_JOBS: dict[str, dict] = {}

load_asr_env()


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # WHY: pip 설치 훅이 빠진 PEP660 editable도, 서버 한 번 뜨면 스케줄러가 붙는다.
    try:
        from sentence_reading.autostart import ensure_registered

        ensure_registered(quiet=True)
    except Exception:
        pass
    yield


app = FastAPI(
    title="A-sentence-reading",
    version="0.2.3",
    description="One-sentence PDF/DOCX reader with Gemini debone + title cache.",
    lifespan=_lifespan,
)


def _job_set(job_id: str, *, percent: int, stage: str, message: str = "") -> None:
    job = _JOBS.get(job_id)
    if not job or job.get("done"):
        return
    job["percent"] = max(0, min(100, int(percent)))
    job["stage"] = stage
    if message:
        job["message"] = message


def _remember_session(session: PaperSession) -> str:
    session_id = f"ses_{uuid.uuid4().hex[:12]}"
    session.clamp_indices()
    _SESSIONS[session_id] = session
    while len(_SESSIONS) > 8:
        oldest = next(iter(_SESSIONS))
        if oldest == session_id:
            break
        del _SESSIONS[oldest]
    return session_id


def _finish_job(job_id: str, data: dict, *, message: str = "완료") -> None:
    job = _JOBS.get(job_id)
    if job is None:
        return
    job["percent"] = 100
    job["stage"] = "done"
    job["message"] = message
    job["result"] = data
    job["done"] = True


@app.get("/api/status")
def status() -> dict:
    """기동 확인."""
    return {
        "ok": True,
        "stage": "m4",
        "pdf_extract": True,
        "sentence_split": True,
        "gemini_debone": gemini_available(),
        "paper_cache": True,
        "docx_extract": True,
        "version": "0.2.3",
    }


@app.get("/api/session/mock")
def session_mock() -> dict:
    data = build_mock_session().to_public_dict()
    data["ok"] = True
    data["session_id"] = "ses_mock"
    data["debone"] = False
    return data


@app.get("/api/cache/papers")
def cache_papers() -> dict:
    """보관된 논문 목록 (제목 기준)."""
    return {"ok": True, "papers": list_cached_papers()}


@app.post("/api/cache/papers/{cache_id}/open")
def cache_open(cache_id: str) -> JSONResponse:
    """보관본을 즉시 세션으로 연다."""
    loaded = load_cached_session(cache_id)
    if loaded is None:
        return JSONResponse(
            status_code=404,
            content={
                "ok": False,
                "error": "cache_not_found",
                "message": "보관된 논문을 찾을 수 없습니다.",
            },
        )
    session, info = loaded
    session_id = _remember_session(session)
    data = session.to_public_dict()
    data["ok"] = True
    data["session_id"] = session_id
    data["debone"] = bool(info.get("debone"))
    data["from_cache"] = True
    data["cache_id"] = cache_id
    data["warnings"] = []
    return JSONResponse(data)


@app.delete("/api/cache/papers/{cache_id}")
def cache_delete(cache_id: str) -> JSONResponse:
    """보관(증류)본 삭제 — 다음에 같은 파일을 열면 다시 분석."""
    deleted = delete_cached_paper(cache_id=cache_id)
    if deleted is None:
        return JSONResponse(
            status_code=404,
            content={
                "ok": False,
                "error": "cache_not_found",
                "message": "삭제할 보관본을 찾지 못했습니다.",
            },
        )
    return JSONResponse(
        {
            "ok": True,
            "deleted_id": deleted.get("id"),
            "title": deleted.get("title"),
            "source": deleted.get("source"),
        }
    )


@app.post("/api/cache/delete")
async def cache_delete_by_meta(payload: dict = Body(...)) -> JSONResponse:
    """cache_id 없거나 모를 때 title+source 로 삭제."""
    cache_id = str(payload.get("cache_id") or "").strip() or None
    title = str(payload.get("title") or "").strip() or None
    source = str(payload.get("source") or "").strip() or None
    if not cache_id and not title:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": "missing_key",
                "message": "cache_id 또는 title 이 필요합니다.",
            },
        )
    deleted = delete_cached_paper(cache_id=cache_id, title=title, source=source)
    if deleted is None:
        return JSONResponse(
            status_code=404,
            content={
                "ok": False,
                "error": "cache_not_found",
                "message": "삭제할 보관본을 찾지 못했습니다.",
            },
        )
    return JSONResponse(
        {
            "ok": True,
            "deleted_id": deleted.get("id"),
            "title": deleted.get("title"),
            "source": deleted.get("source"),
        }
    )


@app.get("/api/session/{session_id}")
def session_get(session_id: str) -> JSONResponse:
    if session_id == "ses_mock":
        data = build_mock_session().to_public_dict()
        data["ok"] = True
        data["session_id"] = "ses_mock"
        return JSONResponse(data)
    session = _SESSIONS.get(session_id)
    if session is None:
        return JSONResponse(
            status_code=404,
            content={
                "ok": False,
                "error": "session_not_found",
                "message": "세션을 찾을 수 없습니다.",
            },
        )
    data = session.to_public_dict()
    data["ok"] = True
    data["session_id"] = session_id
    return JSONResponse(data)


@app.get("/api/ingest/jobs/{job_id}")
def ingest_job_status(job_id: str) -> JSONResponse:
    """업로드·정제 진행률 폴링."""
    job = _JOBS.get(job_id)
    if job is None:
        return JSONResponse(
            status_code=404,
            content={
                "ok": False,
                "error": "job_not_found",
                "message": "작업을 찾을 수 없습니다.",
            },
        )
    out: dict = {
        "ok": True,
        "job_id": job_id,
        "percent": job.get("percent", 0),
        "stage": job.get("stage", ""),
        "message": job.get("message", ""),
        "done": bool(job.get("done")),
    }
    if job.get("error"):
        out["ok"] = False
        out["error"] = "ingest_failed"
        out["message"] = job["error"]
        out["done"] = True
        return JSONResponse(out)
    if job.get("done") and isinstance(job.get("result"), dict):
        out.update(job["result"])
        out["percent"] = 100
        out["done"] = True
    return JSONResponse(out)


def _source_kind(filename: str) -> str | None:
    lower = (filename or "").lower()
    if lower.endswith(".pdf"):
        return "pdf"
    if lower.endswith(".docx"):
        return "docx"
    return None


async def _run_ingest_job(job_id: str, tmp_path: Path, filename: str, kind: str) -> None:
    warnings: list[str] = []
    try:
        label = "PDF" if kind == "pdf" else "Word"
        _job_set(job_id, percent=5, stage="extract", message=f"{label} 읽는 중")
        try:
            if kind == "pdf":
                text = await asyncio.to_thread(pdf_extract.extract_text, tmp_path)
            else:
                text = await asyncio.to_thread(docx_extract.extract_text, tmp_path)
        except ValueError as exc:
            if str(exc) == "encrypted_pdf":
                raise RuntimeError("암호로 보호된 PDF는 열 수 없습니다.") from exc
            raise
        except Exception as exc:
            raise RuntimeError(f"{label} 텍스트 추출 실패: {exc}") from exc

        # WHY: 파일명 말고 논문 제목 — 원문 앞부분에 캐시 제목이 있으면 즉시 로드
        _job_set(job_id, percent=12, stage="cache", message="제목으로 보관본 찾는 중")
        hit = await asyncio.to_thread(find_cached_by_text, text, source=kind)
        if hit and hit.get("id"):
            loaded = await asyncio.to_thread(load_cached_session, str(hit["id"]))
            if loaded is not None:
                session, info = loaded
                # WHY: 옛 docx 캐시가 그림 0장으로 저장된 경우 재추출
                if not (kind == "docx" and len(session.figures) == 0):
                    session_id = _remember_session(session)
                    data = session.to_public_dict()
                    data["ok"] = True
                    data["session_id"] = session_id
                    data["debone"] = bool(info.get("debone"))
                    data["from_cache"] = True
                    data["cache_id"] = hit["id"]
                    data["source"] = kind
                    data["warnings"] = []
                    _finish_job(job_id, data, message="보관본에서 불러옴")
                    return

        _job_set(job_id, percent=15, stage="figures", message="그림 찾는 중")
        try:
            if kind == "pdf":
                figures = await asyncio.to_thread(pdf_extract.extract_figures, tmp_path)
            else:
                figures = await asyncio.to_thread(docx_extract.extract_figures, tmp_path)
        except Exception:
            figures = []
            if kind == "docx":
                warnings.append("docx_figures_partial")

        debone_ok = False
        sentences = []
        if gemini_available() and text.strip():

            def on_progress(done: int, total: int) -> None:
                if total <= 0:
                    return
                # 25% ~ 92% 구간을 청크 진행에 사용
                pct = 25 + int(67 * (done / total))
                _job_set(
                    job_id,
                    percent=pct,
                    stage="debone",
                    message=f"다듬는 중 {done}/{total}",
                )

            _job_set(job_id, percent=25, stage="debone", message="다듬기 시작")
            result: DeboneResult = await asyncio.to_thread(
                debone_sentences, text, on_progress
            )
            if result.ok and result.sentences:
                sentences = result.sentences
                debone_ok = True
                if result.warning:
                    warnings.append(result.warning)
            else:
                warnings.append(result.warning or "gemini_debone_failed")
                _job_set(job_id, percent=90, stage="split", message="기본 문장 나누기")
                sentences = await asyncio.to_thread(split_into_sentences, text)
        else:
            if not gemini_available():
                warnings.append("gemini_key_missing")
            _job_set(job_id, percent=70, stage="split", message="문장 나누는 중")
            sentences = await asyncio.to_thread(split_into_sentences, text)

        _job_set(job_id, percent=95, stage="save", message="거의 끝")
        title = Path(filename).stem or "Untitled"
        for s in sentences:
            if s.section == "title" and s.text.strip():
                title = s.text.strip()
                break

        session = PaperSession(
            title=title,
            figures=figures,
            sentences=sentences,
        )
        session_id = _remember_session(session)

        cache_entry = await asyncio.to_thread(
            save_paper_session, session, debone=debone_ok, source=kind
        )
        if cache_entry is None and debone_ok:
            warnings.append("cache_skip_short_title")

        data = session.to_public_dict()
        data["ok"] = True
        data["session_id"] = session_id
        data["debone"] = debone_ok
        data["warnings"] = warnings
        data["from_cache"] = False
        data["source"] = kind
        if cache_entry:
            data["cache_id"] = cache_entry.get("id")
            data["cached"] = True

        _finish_job(
            job_id,
            data,
            message="완료 · 제목으로 보관됨" if cache_entry else "완료",
        )
    except Exception as exc:  # noqa: BLE001
        job = _JOBS.get(job_id)
        if job is not None:
            job["done"] = True
            job["error"] = str(exc)
            job["percent"] = job.get("percent", 0)
            job["stage"] = "error"
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        # 오래된 job 정리
        while len(_JOBS) > 12:
            oldest = next(iter(_JOBS))
            if oldest == job_id:
                break
            del _JOBS[oldest]


@app.post("/api/ingest")
async def ingest(file: UploadFile = File(...)) -> JSONResponse:
    """PDF/DOCX 업로드 → 백그라운드 정제. job_id 로 진행률 폴링."""
    filename = file.filename or "document.pdf"
    kind = _source_kind(filename)
    if kind is None:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": "unsupported_type",
                "message": "PDF 또는 Word(.docx)만 업로드할 수 있습니다. (옛 .doc 은 docx로 저장해 주세요)",
            },
        )

    raw = await file.read()
    if len(raw) > _MAX_UPLOAD_BYTES:
        return JSONResponse(
            status_code=413,
            content={
                "ok": False,
                "error": "file_too_large",
                "message": "파일이 너무 큽니다 (최대 50MB).",
            },
        )

    if kind == "pdf":
        if len(raw) < 5 or not raw.startswith(b"%PDF"):
            return JSONResponse(
                status_code=400,
                content={
                    "ok": False,
                    "error": "invalid_pdf",
                    "message": "유효한 PDF가 아닙니다.",
                },
            )
        suffix = ".pdf"
    else:
        # docx = ZIP (PK)
        if len(raw) < 4 or raw[:2] != b"PK":
            return JSONResponse(
                status_code=400,
                content={
                    "ok": False,
                    "error": "invalid_docx",
                    "message": "유효한 Word(.docx)가 아닙니다.",
                },
            )
        suffix = ".docx"

    job_id = f"job_{uuid.uuid4().hex[:12]}"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(raw)
        tmp_path = Path(tmp.name)

    _JOBS[job_id] = {
        "percent": 1,
        "stage": "queued",
        "message": "시작해요",
        "done": False,
        "error": None,
        "result": None,
    }
    asyncio.create_task(_run_ingest_job(job_id, tmp_path, filename, kind))
    return JSONResponse(
        {
            "ok": True,
            "job_id": job_id,
            "percent": 1,
            "message": "업로드 완료, 읽기 시작",
        }
    )


_DEBUG_LOG = Path(__file__).resolve().parents[3] / "logs" / "veil_debug.log"


@app.post("/api/debug/veil-log")
async def veil_debug_log(payload: dict = Body(default_factory=dict)) -> dict:
    """에이전트가 듀얼모니터 가림 실패를 추적할 때 클라이언트가 남기는 단계 로그."""
    try:
        _DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
        line = payload if isinstance(payload, dict) else {"raw": str(payload)}
        import json
        from datetime import datetime, timezone

        row = {"ts": datetime.now(timezone.utc).isoformat(), **line}
        with _DEBUG_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@app.get("/api/debug/veil-log")
def veil_debug_log_get() -> dict:
    if not _DEBUG_LOG.is_file():
        return {"ok": True, "lines": []}
    text = _DEBUG_LOG.read_text(encoding="utf-8", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip()][-80:]
    return {"ok": True, "lines": lines, "path": str(_DEBUG_LOG)}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")


@app.get("/veil.html")
def veil_page() -> FileResponse:
    return FileResponse(_STATIC_DIR / "veil.html")


app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
