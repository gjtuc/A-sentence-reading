"""
무엇을: 로컬 HTTP — 정적 UI + status/mock/ingest 자리.
왜: 브라우저에서 Immersive식 문장 패널을 바로 검증한다.
다음에: 업로드 → extract → sentences → 세션 저장.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from sentence_reading.models import build_mock_session

# WHY: static은 패키지 옆 — setuptools package-data와 개발 모드 모두에서 찾기 쉽게.
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(
    title="A-sentence-reading",
    version="0.0.1",
    description="Skeleton: mock UI + PDF stubs. See docs/ARCHITECTURE.md.",
)


@app.get("/api/status")
def status() -> dict:
    """기동 확인. pdf_extract=false 는 스켈레톤 계약."""
    return {
        "ok": True,
        "stage": "skeleton",
        "pdf_extract": False,
        "sentence_split": False,
        "version": "0.0.1",
    }


@app.get("/api/session/mock")
def session_mock() -> dict:
    """
    UI 데모용 고정 세션.

    # INVARIANT: 프론트는 figure_index / sentence_index를 독립으로만 움직여야 한다.
    """
    return build_mock_session().to_public_dict()


@app.post("/api/ingest")
async def ingest() -> JSONResponse:
    """
    PDF 업로드 자리.

    # WHY: 스켈레톤에서는 501 — extract/sentences가 NotImplemented.
    # NEXT: UploadFile → temp path → extract_figures + extract_text + split_into_sentences.
    """
    return JSONResponse(
        status_code=501,
        content={
            "ok": False,
            "error": "not_implemented",
            "message": "PDF ingest is stubbed. Use GET /api/session/mock for the UI shell.",
        },
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")


# /static/styles.css, /static/app.js
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
