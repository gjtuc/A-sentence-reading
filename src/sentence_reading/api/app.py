"""
무엇을: 로컬 HTTP — 정적 UI + status/mock/ingest(+debone·vision OCR 라우터·제목 캐시).
왜: 브라우저에서 Immersive식 문장 패널을 바로 검증한다.
다음에: 세션 LRU·caption 보강.
"""

from __future__ import annotations

import asyncio
import hashlib
import tempfile
import uuid
import urllib.parse
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from sentence_reading.cache.paper_cache import (
    attach_source_file,
    delete_cached_paper,
    find_cached_by_text,
    get_source_path,
    list_cached_papers,
    load_cached_session,
    save_paper_session,
)
from sentence_reading.docx import extract as docx_extract
from sentence_reading.llm.auth_accounts import (
    get_user_record,
    link_provider,
    lookup_uid,
    normalize_email,
    public_user_with_providers,
    pull_accounts_from_gcs,
    resolve_or_create,
    unlink_provider,
    verify_password,
)
from sentence_reading.llm.auth_google import (
    COOKIE_NAME,
    SESSION_MAX_AGE_SEC,
    AuthUser,
    auth_client_id,
    auth_enabled,
    auth_status_fields,
    cookie_secure,
    email_auth_enabled,
    issue_oauth_state,
    issue_session_token,
    parse_oauth_state,
    parse_session_token,
    reset_gcs_uid,
    set_gcs_uid,
    verify_google_id_token,
)
from sentence_reading.llm.auth_kakao import (
    exchange_code as kakao_exchange_code,
    kakao_authorize_url,
    kakao_enabled,
)
from sentence_reading.llm.debone import DeboneResult, debone_sentences
from sentence_reading.llm.env import gemini_available, load_asr_env
from sentence_reading.llm.translate_section import translate_worker_count
from sentence_reading.llm.richtext import plain_text
from sentence_reading.llm.gcs_sync import gcs_status
from sentence_reading.llm.notes_gcs import (
    download_notes_store,
    empty_notes_store,
    push_notes_store,
)
from sentence_reading.llm.voice_gcs import (
    VOICE_BLOB_KEY_MAX,
    VOICE_BLOB_MAX_BYTES,
    download_voice_blob,
    upload_voice_blob,
)
from sentence_reading.llm.tts import (
    CURATED_VOICES,
    synthesize_mp3,
    tts_available,
)
from sentence_reading.llm.tts_speak import spoken_text_for_tts
from sentence_reading.llm.typography import PIPELINE_VERSION, normalize_scientific_glyphs
from sentence_reading.llm.vision_ocr import recover_pdf_text
from sentence_reading.models import Figure, PaperSession, Sentence, build_mock_session
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
    try:
        pull_accounts_from_gcs()
    except Exception:
        pass
    yield


app = FastAPI(
    title="A-sentence-reading",
    version="0.2.63",
    description="One-sentence PDF/DOCX reader with Gemini debone, vision OCR, Cloud TTS.",
    lifespan=_lifespan,
)


class _GcsUidMiddleware(BaseHTTPMiddleware):
    """쿠키 세션 → 요청 동안 GCS personal_object_name 용 UID."""

    async def dispatch(self, request: Request, call_next):
        user = parse_session_token(request.cookies.get(COOKIE_NAME))
        request.state.auth_user = user
        set_gcs_uid(user.uid if user else None)
        try:
            return await call_next(request)
        finally:
            reset_gcs_uid()


app.add_middleware(_GcsUidMiddleware)


def _request_user(request: Request) -> AuthUser | None:
    user = getattr(request.state, "auth_user", None)
    return user if isinstance(user, AuthUser) else None


def _job_set(job_id: str, *, percent: int, stage: str, message: str = "") -> None:
    job = _JOBS.get(job_id)
    if not job or job.get("done"):
        return
    job["percent"] = max(0, min(100, int(percent)))
    job["stage"] = stage
    if message:
        job["message"] = message


def _job_publish_partial(job_id: str, data: dict, *, message: str = "") -> None:
    """
    design/45 — done 전에 세션을 열어 읽기 시작.
    job["result"] 만 갱신 (done=False 유지).
    """
    job = _JOBS.get(job_id)
    if not job or job.get("done"):
        return
    payload = dict(data)
    payload["ok"] = True
    payload["translate_pending"] = True
    job["result"] = payload
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
def status(request: Request) -> dict:
    """기동 확인."""
    user = _request_user(request)
    return {
        "ok": True,
        "stage": "m4",
        "pdf_extract": True,
        "sentence_split": True,
        "gemini_debone": gemini_available(),
        "vision_ocr": gemini_available(),
        "tts": tts_available(),
        "tts_cache_native_rate": True,
        "tts_stretch": "signalsmith",
        "gcs": gcs_status(),
        "auth": auth_status_fields(user),
        "paper_cache": True,
        "docx_extract": True,
        "pipeline_version": PIPELINE_VERSION,
        "progress_restore": True,
        "version": "0.2.63",
        "usage_meter": True,
        "fig_ref_hints": True,
        "cite_ref_open": True,
        "cite_display_clean": True,
        "ko_word_wrap": True,
        "section_review_flow": True,
        "section_review_voice_seq": True,
        "section_review_optional": True,
        "section_review_voice_clip_actions": True,
        "section_review_flow_edit": True,
        "compound_figures": False,
        "reading_order": True,
        "github_cd": True,
        "mobile_flutter_scaffold": True,
        "mobile_android_platform": True,
        "translate_en_ko": gemini_available(),
        "translate_pipeline": True,
        "translate_side_by_side": True,
        "translate_ingest_sections": True,
        "translate_ingest_only": True,
        "translate_live_fallback": False,
        "translate_progressive": True,
        "translate_parallel": True,
        "translate_workers": translate_worker_count(),
        "stt_browser": True,
        "stt_server": gemini_available(),
        "tab_close": True,
    }


def _session_response(user: AuthUser, *, message: str = "logged_in") -> JSONResponse:
    token = issue_session_token(user)
    resp = JSONResponse(
        {
            "ok": True,
            "user": public_user_with_providers(user),
            "gcs_user_scoped": True,
            "message": message,
        }
    )
    resp.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=cookie_secure(),
        max_age=SESSION_MAX_AGE_SEC,
        path="/",
    )
    return resp


def _kakao_redirect_uri(request: Request) -> str:
    # WHY: 콘솔에 등록한 Redirect URI 와 바이트 단위로 같아야 함
    return str(request.base_url).rstrip("/") + "/api/auth/kakao/callback"


@app.get("/api/auth/status")
def auth_status(request: Request) -> dict:
    user = _request_user(request)
    st = auth_status_fields(user)
    return {"ok": True, **st}


@app.post("/api/auth/google")
async def auth_google_login(request: Request, payload: dict = Body(...)) -> JSONResponse:
    """Google Identity Services credential → 세션 (또는 계정 연결)."""
    if not auth_client_id():
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": "auth_disabled",
                "message": "ASR_GOOGLE_CLIENT_ID 를 설정하면 Google 로그인을 쓸 수 있습니다.",
            },
        )
    credential = ""
    mode = "login"
    if isinstance(payload, dict):
        credential = str(payload.get("credential") or payload.get("id_token") or "")
        mode = str(payload.get("mode") or "login").strip().lower()
    try:
        ident = verify_google_id_token(credential)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            status_code=401,
            content={
                "ok": False,
                "error": "invalid_token",
                "message": f"Google 로그인 검증 실패: {exc}"[:240],
            },
        )
    try:
        if mode == "link":
            cur = _request_user(request)
            if cur is None:
                return JSONResponse(
                    status_code=401,
                    content={
                        "ok": False,
                        "error": "auth_required",
                        "message": "연결하려면 먼저 로그인하세요.",
                    },
                )
            user = link_provider(
                cur.uid,
                "google",
                ident.uid,
                email=ident.email,
                name=ident.name,
                picture=ident.picture,
            )
            return _session_response(user, message="linked")
        user = resolve_or_create(
            "google",
            ident.uid,
            email=ident.email,
            name=ident.name,
            picture=ident.picture,
        )
    except ValueError as exc:
        code = str(exc)
        status = 409 if code == "conflict" else 400
        return JSONResponse(
            status_code=status,
            content={
                "ok": False,
                "error": code,
                "message": {
                    "conflict": "이 Google 계정은 이미 다른 사용자에 연결되어 있습니다.",
                }.get(code, str(exc)),
            },
        )
    return _session_response(user)


@app.get("/api/auth/kakao/start")
def auth_kakao_start(request: Request, mode: str = "login") -> Response:
    if not kakao_enabled():
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": "kakao_disabled",
                "message": "ASR_KAKAO_REST_API_KEY 를 설정하세요.",
            },
        )
    m = (mode or "login").strip().lower()
    if m not in ("login", "link"):
        m = "login"
    link_uid = None
    if m == "link":
        cur = _request_user(request)
        if cur is None:
            return JSONResponse(
                status_code=401,
                content={
                    "ok": False,
                    "error": "auth_required",
                    "message": "연결하려면 먼저 로그인하세요.",
                },
            )
        link_uid = cur.uid
    state = issue_oauth_state(m, link_uid=link_uid)
    url = kakao_authorize_url(
        redirect_uri=_kakao_redirect_uri(request), state=state
    )
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url, status_code=302)


@app.get("/api/auth/kakao/callback")
def auth_kakao_callback(
    request: Request, code: str = "", state: str = "", error: str = ""
) -> Response:
    from fastapi.responses import RedirectResponse

    if error:
        return RedirectResponse(
            "/?auth_error=kakao_" + urllib.parse.quote(error), status_code=302
        )
    parsed = parse_oauth_state(state)
    if not parsed:
        return RedirectResponse("/?auth_error=bad_state", status_code=302)
    try:
        profile = kakao_exchange_code(
            code, redirect_uri=_kakao_redirect_uri(request)
        )
        subject = str(profile["subject"])
        if parsed["mode"] == "link":
            uid = parsed.get("link_uid") or ""
            if not uid:
                return RedirectResponse("/?auth_error=link_uid", status_code=302)
            user = link_provider(
                uid,
                "kakao",
                subject,
                email=str(profile.get("email") or ""),
                name=str(profile.get("name") or ""),
                picture=str(profile.get("picture") or ""),
            )
            msg = "linked"
        else:
            user = resolve_or_create(
                "kakao",
                subject,
                email=str(profile.get("email") or ""),
                name=str(profile.get("name") or ""),
                picture=str(profile.get("picture") or ""),
            )
            msg = "logged_in"
    except ValueError as exc:
        err = str(exc)
        if err == "conflict":
            return RedirectResponse("/?auth_error=conflict", status_code=302)
        return RedirectResponse(
            "/?auth_error=" + urllib.parse.quote(err[:80]), status_code=302
        )
    resp = RedirectResponse("/?auth=" + msg, status_code=302)
    resp.set_cookie(
        key=COOKIE_NAME,
        value=issue_session_token(user),
        httponly=True,
        samesite="lax",
        secure=cookie_secure(),
        max_age=SESSION_MAX_AGE_SEC,
        path="/",
    )
    return resp


@app.post("/api/auth/email/register")
async def auth_email_register(payload: dict = Body(...)) -> JSONResponse:
    if not email_auth_enabled():
        return JSONResponse(
            status_code=503,
            content={"ok": False, "error": "email_disabled", "message": "이메일 가입이 꺼져 있습니다."},
        )
    email = str(payload.get("email") or "") if isinstance(payload, dict) else ""
    password = str(payload.get("password") or "") if isinstance(payload, dict) else ""
    name = str(payload.get("name") or "") if isinstance(payload, dict) else ""
    try:
        em = normalize_email(email)
        if not em:
            raise ValueError("bad_email")
        if lookup_uid("email", em):
            raise ValueError("email_taken")
        user = resolve_or_create(
            "email", em, email=em, name=name, password=password
        )
    except ValueError as exc:
        code = str(exc)
        messages = {
            "bad_email": "이메일 형식이 올바르지 않습니다.",
            "email_taken": "이미 가입된 이메일입니다. 로그인하세요.",
            "password_too_short": "비밀번호는 8자 이상이어야 합니다.",
        }
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": code, "message": messages.get(code, code)},
        )
    return _session_response(user, message="registered")


@app.post("/api/auth/email/login")
async def auth_email_login(payload: dict = Body(...)) -> JSONResponse:
    if not email_auth_enabled():
        return JSONResponse(
            status_code=503,
            content={"ok": False, "error": "email_disabled", "message": "이메일 로그인이 꺼져 있습니다."},
        )
    email = str(payload.get("email") or "") if isinstance(payload, dict) else ""
    password = str(payload.get("password") or "") if isinstance(payload, dict) else ""
    em = normalize_email(email)
    if not em:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": "bad_email",
                "message": "이메일 형식이 올바르지 않습니다.",
            },
        )
    uid = lookup_uid("email", em)
    if not uid:
        return JSONResponse(
            status_code=401,
            content={
                "ok": False,
                "error": "bad_credentials",
                "message": "이메일 또는 비밀번호가 올바르지 않습니다.",
            },
        )
    row = get_user_record(uid) or {}
    ph = str(row.get("password_hash") or "")
    if not ph or not verify_password(password, ph):
        return JSONResponse(
            status_code=401,
            content={
                "ok": False,
                "error": "bad_credentials",
                "message": "이메일 또는 비밀번호가 올바르지 않습니다.",
            },
        )
    user = AuthUser(
        uid=uid,
        email=str(row.get("email") or em),
        name=str(row.get("name") or ""),
        picture=str(row.get("picture") or ""),
    )
    return _session_response(user)


@app.post("/api/auth/email/link")
async def auth_email_link(request: Request, payload: dict = Body(...)) -> JSONResponse:
    cur = _request_user(request)
    if cur is None:
        return JSONResponse(
            status_code=401,
            content={"ok": False, "error": "auth_required", "message": "먼저 로그인하세요."},
        )
    if not email_auth_enabled():
        return JSONResponse(
            status_code=503,
            content={"ok": False, "error": "email_disabled", "message": "이메일 연결이 꺼져 있습니다."},
        )
    email = str(payload.get("email") or "") if isinstance(payload, dict) else ""
    password = str(payload.get("password") or "") if isinstance(payload, dict) else ""
    try:
        em = normalize_email(email)
        if not em:
            raise ValueError("bad_email")
        user = link_provider(cur.uid, "email", em, email=em, password=password)
    except ValueError as exc:
        code = str(exc)
        messages = {
            "conflict": "이 이메일은 이미 다른 계정에 연결되어 있습니다.",
            "bad_email": "이메일 형식이 올바르지 않습니다.",
            "password_too_short": "비밀번호는 8자 이상이어야 합니다.",
        }
        return JSONResponse(
            status_code=409 if code == "conflict" else 400,
            content={"ok": False, "error": code, "message": messages.get(code, code)},
        )
    return _session_response(user, message="linked")


@app.post("/api/auth/unlink")
async def auth_unlink(request: Request, payload: dict = Body(...)) -> JSONResponse:
    cur = _request_user(request)
    if cur is None:
        return JSONResponse(
            status_code=401,
            content={"ok": False, "error": "auth_required", "message": "먼저 로그인하세요."},
        )
    provider = str(payload.get("provider") or "") if isinstance(payload, dict) else ""
    try:
        user = unlink_provider(cur.uid, provider)
    except ValueError as exc:
        code = str(exc)
        messages = {
            "last_provider": "마지막 로그인 수단은 해제할 수 없습니다.",
            "not_linked": "연결되어 있지 않습니다.",
        }
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": code, "message": messages.get(code, code)},
        )
    return _session_response(user, message="unlinked")


@app.post("/api/stt/compare")
async def stt_compare(payload: dict = Body(...)) -> dict:
    """원문 vs 인식 단어 diff — 점수 없음 (design/37)."""
    from sentence_reading.stt.compare import diff_tokens

    if not isinstance(payload, dict):
        return {"ok": False, "error": "invalid_body"}
    expected = payload.get("expected")
    heard = payload.get("heard")
    # WHY: score 필드를 응답에 넣지 않음 — 채점 UI 유혹 차단
    result = diff_tokens(expected, heard)
    if result.get("ok"):
        assert "score" not in result
        assert "grade" not in result
        assert "accuracy" not in result
    return result


@app.post("/api/stt/recognize")
async def stt_recognize(
    file: UploadFile = File(...),
    expected: str = Form(""),
) -> dict:
    """연습 오디오 → 영어 전사 (+선택 compare). 점수 없음 (design/38)."""
    from sentence_reading.stt.compare import diff_tokens
    from sentence_reading.stt.recognize import recognize_english_audio

    if not gemini_available():
        return {"ok": False, "error": "gemini_unavailable"}
    try:
        data = await file.read()
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": "recognize_failed",
            "message": str(exc)[:200],
        }
    mime = file.content_type or "application/octet-stream"
    try:
        result = await asyncio.to_thread(recognize_english_audio, data, mime)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": "recognize_failed",
            "message": str(exc)[:200],
        }
    if not result.get("ok"):
        return result
    out: dict = {
        "ok": True,
        "heard": result.get("heard") or "",
        "engine": result.get("engine") or "gemini",
    }
    exp = expected if isinstance(expected, str) else ""
    if exp.strip():
        cmp = diff_tokens(exp, out["heard"])
        if cmp.get("ok"):
            assert "score" not in cmp
        out["compare"] = cmp
    assert "score" not in out
    return out


@app.post("/api/cite/resolve")
async def cite_resolve(payload: dict = Body(...)) -> dict:
    """문헌 문자열 → 원문 URL (design/41 · DOI · Crossref · Scholar)."""
    from sentence_reading.llm.crossref_resolve import resolve_citation

    text = payload.get("text") if isinstance(payload, dict) else None
    if text is None:
        text = ""
    if not isinstance(text, str):
        return {"ok": False, "error": "invalid_text", "url": "", "source": ""}
    try:
        result = await asyncio.to_thread(resolve_citation, text)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": "resolve_failed",
            "message": str(exc)[:200],
            "url": "",
            "source": "",
        }
    return result


@app.post("/api/translate")
async def translate_sentence(payload: dict = Body(...)) -> dict:
    """영→한 번역 (design/35 simple · design/36 pipeline 기본)."""
    from sentence_reading.llm.translate import translate_dispatch

    if not gemini_available():
        return {"ok": False, "error": "gemini_unavailable"}
    text = payload.get("text") if isinstance(payload, dict) else None
    if text is None:
        text = ""
    if not isinstance(text, str):
        return {"ok": False, "error": "invalid_text"}
    mode = "pipeline"
    if isinstance(payload, dict) and payload.get("mode") is not None:
        mode = str(payload.get("mode") or "pipeline")
    try:
        result = await asyncio.to_thread(translate_dispatch, text, mode)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": "translate_failed",
            "message": str(exc)[:200],
        }
    if not result.get("ok"):
        return result
    return {
        "ok": True,
        "ko": result["ko"],
        "source_lang": "en",
        "target_lang": "ko",
        "mode": result.get("mode") or mode,
        "cached": bool(result.get("cached")),
        "stages_done": list(result.get("stages_done") or []),
    }


@app.get("/api/usage")
def usage_me(request: Request) -> dict:
    """관리자만: 본인 사용량 · 추정 비용 (일반 유저 UI/API 비공개)."""
    from sentence_reading.llm.usage_meter import is_admin_email, public_usage

    user = _request_user(request)
    if not user:
        return {"ok": False, "error": "auth_required"}
    if not is_admin_email(user.email):
        return {"ok": False, "error": "forbidden"}
    return public_usage(user.uid, email=user.email or "")


@app.get("/api/usage/admin")
def usage_admin(request: Request) -> dict:
    """관리자: 전체 유저 사용량."""
    from sentence_reading.llm.usage_meter import admin_usage_report, is_admin_email

    user = _request_user(request)
    if not user:
        return {"ok": False, "error": "auth_required"}
    if not is_admin_email(user.email):
        return {"ok": False, "error": "forbidden"}
    return admin_usage_report()


@app.post("/api/auth/logout")
def auth_logout() -> JSONResponse:
    resp = JSONResponse({"ok": True, "message": "logged_out"})
    resp.delete_cookie(COOKIE_NAME, path="/", secure=cookie_secure(), samesite="lax")
    return resp


@app.get("/api/voice/blobs")
async def voice_blob_get(request: Request, key: str = "") -> Response:
    """
    blobKey → 오디오 bytes (GCS). IDB miss 시 클라이언트가 호출.
    """
    if auth_enabled() and _request_user(request) is None:
        return JSONResponse(
            status_code=401,
            content={
                "ok": False,
                "available": False,
                "needs_auth": True,
                "error": "auth_required",
                "message": "로그인 후 목소리를 동기화합니다.",
            },
        )
    st = gcs_status()
    if not st.get("enabled") or not st.get("ready"):
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "available": False,
                "error": "gcs_unavailable",
                "message": st.get("message"),
            },
        )
    blob_key = (key or "").strip()
    if not blob_key or len(blob_key) > VOICE_BLOB_KEY_MAX:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "bad_key", "message": "invalid blob key"},
        )
    data = download_voice_blob(blob_key)
    if not data:
        return JSONResponse(
            status_code=404,
            content={"ok": False, "error": "not_found", "message": "voice blob missing"},
        )
    return Response(content=data, media_type="application/octet-stream")


@app.put("/api/voice/blobs")
async def voice_blob_put(request: Request, key: str = "") -> JSONResponse:
    """
    녹음 blob → GCS. query `key` = 노트 store 의 blobKey.
    """
    if auth_enabled() and _request_user(request) is None:
        return JSONResponse(
            {
                "ok": True,
                "available": False,
                "needs_auth": True,
                "uploaded": False,
                "message": "로그인 후 목소리를 동기화합니다.",
            }
        )
    st = gcs_status()
    if not st.get("enabled") or not st.get("ready"):
        return JSONResponse(
            {
                "ok": True,
                "available": False,
                "uploaded": False,
                "message": st.get("message"),
            }
        )
    blob_key = (key or "").strip()
    if not blob_key or len(blob_key) > VOICE_BLOB_KEY_MAX:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "bad_key", "message": "invalid blob key"},
        )
    body = await request.body()
    if not body:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "empty_body", "message": "empty audio"},
        )
    if len(body) > VOICE_BLOB_MAX_BYTES:
        return JSONResponse(
            status_code=413,
            content={
                "ok": False,
                "error": "too_large",
                "message": f"max {VOICE_BLOB_MAX_BYTES} bytes",
            },
        )
    ctype = (request.headers.get("content-type") or "application/octet-stream").split(";")[
        0
    ].strip()
    ok = upload_voice_blob(blob_key, body, content_type=ctype or "application/octet-stream")
    return JSONResponse(
        {
            "ok": True,
            "available": True,
            "uploaded": bool(ok),
            "message": "ok" if ok else "upload_failed",
        }
    )


@app.get("/api/notes/sync")
def notes_sync_get(request: Request) -> dict:
    """GCS 노트 store pull. 버킷 미설정·미준비면 available=false."""
    if auth_enabled() and _request_user(request) is None:
        return {
            "ok": True,
            "available": False,
            "needs_auth": True,
            "store": None,
            "message": "Google 로그인 후 클라우드 노트를 동기화합니다.",
        }
    st = gcs_status()
    if not st.get("enabled") or not st.get("ready"):
        return {
            "ok": True,
            "available": False,
            "store": None,
            "message": st.get("message"),
        }
    if st.get("notes_object") is None:
        return {
            "ok": True,
            "available": False,
            "needs_auth": True,
            "store": None,
            "message": "로그인된 사용자 칸이 없습니다.",
        }
    store = download_notes_store()
    return {
        "ok": True,
        "available": True,
        "store": store if store is not None else empty_notes_store(),
        "message": "ok",
    }


@app.put("/api/notes/sync")
async def notes_sync_put(request: Request, payload: dict = Body(...)) -> JSONResponse:
    """
    로컬 store push — remote∪local 병합 후 GCS 업로드, 병합본 반환.
    """
    if auth_enabled() and _request_user(request) is None:
        return JSONResponse(
            {
                "ok": True,
                "available": False,
                "needs_auth": True,
                "store": payload.get("store") if isinstance(payload, dict) else None,
                "message": "Google 로그인 후 클라우드 노트를 동기화합니다.",
            }
        )
    st = gcs_status()
    if not st.get("enabled") or not st.get("ready"):
        return JSONResponse(
            {
                "ok": True,
                "available": False,
                "store": payload.get("store") if isinstance(payload, dict) else None,
                "message": st.get("message"),
            }
        )
    if st.get("notes_object") is None:
        return JSONResponse(
            {
                "ok": True,
                "available": False,
                "needs_auth": True,
                "store": payload.get("store") if isinstance(payload, dict) else None,
                "message": "로그인된 사용자 칸이 없습니다.",
            }
        )
    local = payload.get("store") if isinstance(payload, dict) else None
    if not isinstance(local, dict):
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "bad_store", "message": "store object required"},
        )
    try:
        merged = push_notes_store(local)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            status_code=502,
            content={
                "ok": False,
                "error": "notes_sync_failed",
                "message": str(exc)[:300],
            },
        )
    return JSONResponse({"ok": True, "available": True, "store": merged, "message": "ok"})


@app.get("/api/tts/voices")
def tts_voices() -> dict:
    """UI용 추천 보이스 목록."""
    return {
        "ok": True,
        "available": tts_available(),
        "voices": CURATED_VOICES,
        "default_voice": "en-US-Neural2-D",
        "default_rate": 1.0,
        "rate_min": 0.5,
        "rate_max": 2.2,
    }


@app.post("/api/tts")
async def tts_synthesize(payload: dict = Body(...)) -> Response:
    """현재 문장 plain text → MP3."""
    if not tts_available():
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": "tts_unavailable",
                "message": "Cloud TTS 자격 증명이 없습니다.",
            },
        )
    text = spoken_text_for_tts(str(payload.get("text") or ""))
    voice = str(payload.get("voice") or "").strip() or None
    if voice in ("undefined", "null", "None"):
        voice = None
    try:
        rate = float(payload.get("speaking_rate", 1.0))
    except (TypeError, ValueError):
        rate = 1.0
    if not text.strip():
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": "empty_text",
                "message": "읽을 문장이 없습니다.",
            },
        )
    try:
        audio = await asyncio.to_thread(
            synthesize_mp3, text, voice=voice, speaking_rate=rate
        )
    except ValueError as exc:
        code = str(exc) or "bad_request"
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": code, "message": str(exc)},
        )
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            status_code=502,
            content={
                "ok": False,
                "error": "tts_failed",
                "message": str(exc),
            },
        )
    return Response(content=audio, media_type="audio/mpeg")


@app.get("/api/session/mock")
def session_mock() -> dict:
    data = build_mock_session().to_public_dict()
    data["ok"] = True
    data["session_id"] = "ses_mock"
    data["debone"] = False
    return data


@app.get("/api/cache/papers")
def cache_papers() -> dict:
    """보관된 논문 목록 (로컬 ∪ GCS index 메타)."""
    try:
        from sentence_reading.llm.papers_gcs import list_merged_paper_entries

        return {"ok": True, "papers": list_merged_paper_entries()}
    except Exception:
        return {"ok": True, "papers": list_cached_papers()}


@app.post("/api/cache/papers/{cache_id}/open")
async def cache_open(cache_id: str) -> JSONResponse:
    """보관본을 즉시 세션으로 연다. 로컬 miss 시 GCS pull · KO 없으면 번역 백필."""
    loaded = load_cached_session(cache_id)
    if loaded is None:
        try:
            from sentence_reading.llm.papers_gcs import ensure_paper_local

            ensure_paper_local(cache_id)
        except Exception:
            pass
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
    src = "pdf"
    # index source 힌트
    try:
        from sentence_reading.cache.paper_cache import list_cached_papers

        for e in list_cached_papers():
            if e.get("id") == cache_id:
                src = str(e.get("source") or "pdf")
                break
    except Exception:
        pass
    session, bf_warn = await _backfill_cached_translations(
        None,
        session,
        kind=src,
        source_path=get_source_path(cache_id),
        content_hash=info.get("content_hash"),
    )
    session_id = _remember_session(session)
    data = session.to_public_dict()
    data["ok"] = True
    data["session_id"] = session_id
    data["debone"] = bool(info.get("debone"))
    data["from_cache"] = True
    data["cache_id"] = cache_id
    data["pipeline_version"] = str(info.get("pipeline_version") or "")
    data["current_pipeline"] = PIPELINE_VERSION
    data["stale"] = bool(info.get("stale"))
    data["has_source"] = bool(info.get("has_source")) or get_source_path(cache_id) is not None
    if info.get("content_hash"):
        data["content_hash"] = info["content_hash"]
    # WHY: stale 도 열어 노트(cache:id) 유지 — 원본 있으면 재분석, 없으면 파일 재업로드
    warnings = ["stale_pipeline"] if info.get("stale") else []
    warnings.extend(bf_warn)
    data["warnings"] = warnings
    return JSONResponse(data)


@app.post("/api/cache/papers/{cache_id}/reanalyze")
async def cache_reanalyze(cache_id: str) -> JSONResponse:
    """보관된 원본(source.pdf|docx)으로 파이프라인 재실행. 같은 cache_id 유지."""
    cid = (cache_id or "").strip()
    try:
        from sentence_reading.llm.papers_gcs import ensure_paper_local

        ensure_paper_local(cid)
    except Exception:
        pass
    src = get_source_path(cid)
    if src is None:
        return JSONResponse(
            status_code=404,
            content={
                "ok": False,
                "error": "source_missing",
                "message": "원본 파일이 없어 재분석할 수 없습니다. PDF/Word를 다시 열어 주세요.",
            },
        )
    kind = "docx" if src.name.lower().endswith(".docx") else "pdf"
    suffix = ".docx" if kind == "docx" else ".pdf"
    try:
        raw = src.read_bytes()
    except OSError as exc:
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "source_read_failed",
                "message": f"원본을 읽지 못했습니다: {exc}",
            },
        )
    if not raw:
        return JSONResponse(
            status_code=404,
            content={
                "ok": False,
                "error": "source_missing",
                "message": "원본 파일이 비어 있습니다.",
            },
        )

    job_id = f"job_{uuid.uuid4().hex[:12]}"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(raw)
        tmp_path = Path(tmp.name)

    filename = src.name
    _JOBS[job_id] = {
        "percent": 1,
        "stage": "queued",
        "message": "재분석 시작",
        "done": False,
        "error": None,
        "result": None,
    }
    content_hash = await asyncio.to_thread(_file_sha256, tmp_path)
    asyncio.create_task(
        _run_ingest_job(
            job_id,
            tmp_path,
            filename,
            kind,
            skip_cache=True,
            content_hash=content_hash,
        )
    )
    return JSONResponse(
        {
            "ok": True,
            "job_id": job_id,
            "cache_id": cid,
            "percent": 1,
            "message": "재분석 시작",
        }
    )


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
        out["translate_pending"] = False
    elif isinstance(job.get("result"), dict):
        # WHY: design/45 — 번역 중에도 세션 열어 읽기
        out.update(job["result"])
        out["done"] = False
        out["translate_pending"] = True
    return JSONResponse(out)


def _source_kind(filename: str) -> str | None:
    lower = (filename or "").lower()
    if lower.endswith(".pdf"):
        return "pdf"
    if lower.endswith(".docx"):
        return "docx"
    return None


def _file_sha256(path: Path) -> str | None:
    """원본 바이트 SHA-256 — 진행 복원 키 (design/05·21)."""
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def _try_cache_hit(
    text: str, kind: str
) -> tuple[PaperSession, dict, dict] | None:
    """보관본 히트 시 (session, info, hit_entry)."""
    hit = find_cached_by_text(text, source=kind)
    if not hit or not hit.get("id"):
        return None
    if str(hit.get("pipeline_version") or "") != PIPELINE_VERSION:
        return None
    loaded = load_cached_session(str(hit["id"]))
    if loaded is None:
        return None
    session, info = loaded
    if kind == "docx" and len(session.figures) == 0:
        return None
    return session, info, hit


async def _backfill_cached_translations(
    job_id: str | None,
    session: PaperSession,
    *,
    kind: str,
    source_path: Path | None,
    content_hash: str | None,
) -> tuple[PaperSession, list[str]]:
    """
    design/42 — 보관본에 KO가 없으면 번역만 채우고 같은 제목 키로 재저장.
    Gemini 없거나 실패해도 원 세션 반환 (fail-soft).
    """
    from sentence_reading.llm.translate_section import (
        enrich_session_translations,
        needs_translate_backfill,
    )

    warnings: list[str] = []
    if not needs_translate_backfill(
        session.sentences, session.figures, session.translate_digests
    ):
        return session, warnings
    if not gemini_available():
        warnings.append("translate_missing")
        warnings.append("translate_skipped_no_gemini")
        return session, warnings
    # WHY: design/43 — 백필도 문장/요지/캡션 단위로 badge 갱신
    def _bf_progress(message: str, fraction: float = 0.0) -> None:
        if not job_id:
            return
        lo, hi = 88, 93
        pct = int(lo + (hi - lo) * max(0.0, min(1.0, fraction)))
        _job_set(job_id, percent=pct, stage="translate", message=message)

    if job_id:
        _job_set(
            job_id,
            percent=88,
            stage="translate",
            message="보관본 번역 채우는 중",
        )
    try:
        sentences, figures, digests, tr_warn = await asyncio.to_thread(
            enrich_session_translations,
            session.sentences,
            session.figures,
            on_progress=_bf_progress,
        )
        warnings.extend(tr_warn)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"translate_backfill_failed:{str(exc)[:80]}")
        return session, warnings

    session.sentences = sentences
    session.figures = figures
    session.translate_digests = digests
    try:
        await asyncio.to_thread(
            save_paper_session,
            session,
            debone=True,
            source=kind,
            source_path=source_path,
            content_hash=content_hash,
        )
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"translate_backfill_save_failed:{str(exc)[:80]}")
    return session, warnings


async def _run_ingest_job(
    job_id: str,
    tmp_path: Path,
    filename: str,
    kind: str,
    *,
    skip_cache: bool = False,
    content_hash: str | None = None,
) -> None:
    warnings: list[str] = []
    try:
        label = "PDF" if kind == "pdf" else "Word"
        if not content_hash:
            content_hash = await asyncio.to_thread(_file_sha256, tmp_path)
        _job_set(job_id, percent=5, stage="extract", message=f"{label} 읽는 중")
        pdf_pages: list[str] | None = None
        try:
            if kind == "pdf":
                pdf_pages = await asyncio.to_thread(
                    pdf_extract.extract_text_by_page, tmp_path
                )
                text = pdf_extract.join_page_texts(pdf_pages)
            else:
                text = await asyncio.to_thread(docx_extract.extract_text, tmp_path)
        except ValueError as exc:
            if str(exc) == "encrypted_pdf":
                raise RuntimeError("암호로 보호된 PDF는 열 수 없습니다.") from exc
            raise
        except Exception as exc:
            raise RuntimeError(f"{label} 텍스트 추출 실패: {exc}") from exc

        # WHY: 파일명 말고 논문 제목 — 원문 앞부분에 캐시 제목이 있으면 즉시 로드
        # 재분석(skip_cache) 또는 원본 백필은 히트 경로에서도 진행
        if not skip_cache:
            _job_set(job_id, percent=10, stage="cache", message="제목으로 보관본 찾는 중")
            cached = await asyncio.to_thread(_try_cache_hit, text, kind)
            if cached is not None:
                session, info, hit = cached
                await asyncio.to_thread(
                    attach_source_file, str(hit["id"]), tmp_path, source=kind
                )
                session, bf_warn = await _backfill_cached_translations(
                    job_id,
                    session,
                    kind=kind,
                    source_path=tmp_path,
                    content_hash=content_hash,
                )
                session_id = _remember_session(session)
                data = session.to_public_dict()
                data["ok"] = True
                data["session_id"] = session_id
                data["debone"] = bool(info.get("debone"))
                data["from_cache"] = True
                data["cache_id"] = hit["id"]
                data["source"] = kind
                data["has_source"] = get_source_path(str(hit["id"])) is not None
                if content_hash:
                    data["content_hash"] = content_hash
                data["warnings"] = list(bf_warn)
                _finish_job(job_id, data, message="보관본에서 불러옴")
                return

        # WHY: PDF만 적응형 vision — 스캔·손상 페이지 복구 후 캐시 재조회
        if kind == "pdf" and pdf_pages is not None:

            def on_recover(
                stage: str, done: int, total: int, message: str
            ) -> None:
                if stage == "quality":
                    pct = 12 + (8 if total and done >= total else 4)
                elif stage == "vision" and total > 0:
                    pct = 20 + int(18 * (done / total))
                else:
                    pct = 18
                _job_set(job_id, percent=pct, stage=stage, message=message)

            _job_set(job_id, percent=12, stage="quality", message="추출 품질 보는 중")
            recovered = await asyncio.to_thread(
                recover_pdf_text, tmp_path, pdf_pages, on_progress=on_recover
            )
            text = recovered.text
            warnings.extend(recovered.warnings)
            if recovered.vision_pages and not skip_cache:
                # 복구 후 제목이 보이면 보관본 재사용
                _job_set(job_id, percent=40, stage="cache", message="복구 후 보관본 확인")
                cached = await asyncio.to_thread(_try_cache_hit, text, kind)
                if cached is not None:
                    session, info, hit = cached
                    await asyncio.to_thread(
                        attach_source_file, str(hit["id"]), tmp_path, source=kind
                    )
                    session, bf_warn = await _backfill_cached_translations(
                        job_id,
                        session,
                        kind=kind,
                        source_path=tmp_path,
                        content_hash=content_hash,
                    )
                    session_id = _remember_session(session)
                    data = session.to_public_dict()
                    data["ok"] = True
                    data["session_id"] = session_id
                    data["debone"] = bool(info.get("debone"))
                    data["from_cache"] = True
                    data["cache_id"] = hit["id"]
                    data["source"] = kind
                    data["has_source"] = get_source_path(str(hit["id"])) is not None
                    if content_hash:
                        data["content_hash"] = content_hash
                    data["warnings"] = list(warnings) + list(bf_warn)
                    _finish_job(job_id, data, message="보관본에서 불러옴")
                    return

        _job_set(job_id, percent=42, stage="figures", message="그림 찾는 중")
        try:
            if kind == "pdf":
                figures = await asyncio.to_thread(pdf_extract.extract_figures, tmp_path)
            else:
                figures = await asyncio.to_thread(docx_extract.extract_figures, tmp_path)
        except Exception:
            figures = []
            if kind == "docx":
                warnings.append("docx_figures_partial")

        # WHY: 캡션의 ◦C 등 lookalike — 문장 경로와 동일 정규화
        if figures:
            figures = [
                Figure(
                    id=f.id,
                    image_src=f.image_src,
                    caption=normalize_scientific_glyphs(f.caption),
                    page_index=f.page_index,
                )
                for f in figures
            ]

        debone_ok = False
        sentences = []
        if gemini_available() and text.strip():

            def on_progress(done: int, total: int) -> None:
                if total <= 0:
                    return
                # 48% ~ 92% 구간 — survey(1단위) + 청크 (앞에 quality/vision 예약)
                pct = 48 + int(44 * (done / total))
                if done <= 0:
                    msg = "논문 훑는 중"
                elif done == 1 and total > 1:
                    msg = "다듬기 시작"
                else:
                    chunk_done = max(0, done - 1)
                    chunk_total = max(1, total - 1)
                    msg = f"다듬는 중 {chunk_done}/{chunk_total}"
                _job_set(
                    job_id,
                    percent=pct,
                    stage="debone",
                    message=msg,
                )

            _job_set(job_id, percent=48, stage="debone", message="논문 훑는 중")
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
            if not gemini_available() and "gemini_key_missing" not in warnings:
                warnings.append("gemini_key_missing")
            _job_set(job_id, percent=70, stage="split", message="문장 나누는 중")
            sentences = await asyncio.to_thread(split_into_sentences, text)

        # WHY: debone 경로도 apply_glossary가 이미 정규화함 — 폴백·누락 lookalike 한 번 더
        sentences = [
            Sentence(
                id=s.id,
                text=normalize_scientific_glyphs(s.text),
                section=s.section,
                start_char=s.start_char,
                end_char=s.end_char,
            )
            for s in sentences
        ]

        # WHY: design/41 — debone이 References를 버려도 원문에서 별도 추출
        from sentence_reading.cite_refs import (
            bibliography_public,
            extract_bibliography,
        )

        references = bibliography_public(extract_bibliography(text))

        title = Path(filename).stem or "Untitled"
        for s in sentences:
            if s.section == "title" and plain_text(s.text):
                title = plain_text(s.text)
                break

        # WHY: design/45 — 번역 전에 영어 세션을 먼저 열어 읽기 시작
        digests: dict = {}
        session = PaperSession(
            title=title,
            figures=figures,
            sentences=sentences,
            translate_digests=digests,
            references=references,
        )
        session_id = _remember_session(session)

        def _pack(*, pending: bool) -> dict:
            d = session.to_public_dict()
            d["ok"] = True
            d["session_id"] = session_id
            d["debone"] = debone_ok
            d["warnings"] = list(warnings)
            d["from_cache"] = False
            d["source"] = kind
            d["translate_pending"] = pending
            if content_hash:
                d["content_hash"] = content_hash
            return d

        _job_set(job_id, percent=88, stage="ready", message="읽기 시작 · 번역 준비")
        early = _pack(pending=True)
        cache_entry = await asyncio.to_thread(
            save_paper_session,
            session,
            debone=debone_ok,
            source=kind,
            source_path=tmp_path,
            content_hash=content_hash,
        )
        if cache_entry is None and debone_ok:
            warnings.append("cache_skip_short_title")
        if cache_entry:
            early["cache_id"] = cache_entry.get("id")
            early["cached"] = True
            early["has_source"] = bool(cache_entry.get("has_source"))
        _job_publish_partial(job_id, early, message="읽기 가능 · 번역 중")

        if gemini_available():
            _job_set(
                job_id,
                percent=90,
                stage="translate",
                message="섹션 번역·요지 정리 중",
            )
            from dataclasses import replace as dc_replace

            from sentence_reading.llm.translate_section import (
                enrich_session_translations,
            )

            def _tr_progress(message: str, fraction: float = 0.0) -> None:
                lo, hi = 90, 97
                pct = int(lo + (hi - lo) * max(0.0, min(1.0, fraction)))
                _job_set(job_id, percent=pct, stage="translate", message=message)

            def _on_item(kind: str, index: int, ko: str, stage: str) -> None:
                # WHY: 보고 있지 않은 문장 데이터만 갱신 — UI 스냅샷 고정은 클라
                if kind == "sentence" and 0 <= index < len(session.sentences):
                    s = session.sentences[index]
                    session.sentences[index] = dc_replace(
                        s, text_ko=ko, text_ko_stage=stage
                    )
                elif kind == "figure" and 0 <= index < len(session.figures):
                    f = session.figures[index]
                    session.figures[index] = dc_replace(
                        f, caption_ko=ko, caption_ko_stage=stage
                    )
                packed = _pack(pending=True)
                if cache_entry:
                    packed["cache_id"] = cache_entry.get("id")
                    packed["cached"] = True
                    packed["has_source"] = bool(cache_entry.get("has_source"))
                _job_publish_partial(job_id, packed)

            try:
                new_s, new_f, digests, tr_warn = await asyncio.to_thread(
                    enrich_session_translations,
                    list(session.sentences),
                    list(session.figures),
                    on_progress=_tr_progress,
                    on_item=_on_item,
                )
                warnings.extend(tr_warn)
                session.sentences = new_s
                session.figures = new_f
                session.translate_digests = digests
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"translate_failed:{str(exc)[:80]}")
        else:
            warnings.append("translate_skipped_no_gemini")

        _job_set(job_id, percent=98, stage="save", message="번역 저장 중")
        cache_entry = await asyncio.to_thread(
            save_paper_session,
            session,
            debone=debone_ok,
            source=kind,
            source_path=tmp_path,
            content_hash=content_hash,
        )
        if cache_entry is None and debone_ok and "cache_skip_short_title" not in warnings:
            warnings.append("cache_skip_short_title")

        data = _pack(pending=False)
        if cache_entry:
            data["cache_id"] = cache_entry.get("id")
            data["cached"] = True
            data["has_source"] = bool(cache_entry.get("has_source"))

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

    content_hash = hashlib.sha256(raw).hexdigest()
    _JOBS[job_id] = {
        "percent": 1,
        "stage": "queued",
        "message": "시작해요",
        "done": False,
        "error": None,
        "result": None,
    }
    asyncio.create_task(
        _run_ingest_job(
            job_id, tmp_path, filename, kind, content_hash=content_hash
        )
    )
    return JSONResponse(
        {
            "ok": True,
            "job_id": job_id,
            "percent": 1,
            "message": "업로드 완료, 읽기 시작",
            "content_hash": content_hash,
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
def index() -> HTMLResponse:
    # WHY: 정적 JS/CSS 캐시 무효화 — 배포 버전이 바뀌면 브라우저가 새 파일을 받음
    html = (_STATIC_DIR / "index.html").read_text(encoding="utf-8")
    html = html.replace("__ASR_ASSET_V__", app.version)
    return HTMLResponse(html)


@app.get("/veil.html")
def veil_page() -> FileResponse:
    return FileResponse(_STATIC_DIR / "veil.html")


app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
