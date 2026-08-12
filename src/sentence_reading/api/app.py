"""
무엇을: 로컬 HTTP — 정적 UI + status/mock/ingest(+debone·vision OCR 라우터·제목 캐시).
왜: 브라우저에서 Immersive식 문장 패널을 바로 검증한다.
다음에: 세션 LRU·caption 보강.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
import uuid
import urllib.parse
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
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
    email_password_auth_enabled,
    issue_oauth_state,
    mobile_kakao_deep_link,
    mobile_magic_deep_link,
    issue_session_token,
    parse_oauth_state,
    parse_session_token,
    reset_gcs_uid,
    set_gcs_uid,
    verify_google_id_token,
)
from sentence_reading.llm.shadowing_practice import shadowing_practice_enabled
from sentence_reading.llm.login_required import (
    is_login_public_path,
    login_required_enabled,
)
from sentence_reading.llm.access_gate import (
    access_gate_enabled,
    invite_ttl_seconds,
    redeem_max_attempts,
    redeem_window_seconds,
    decide_access,
    list_events,
    list_open_invite_meta,
    list_pending,
    mint_invite_code,
    public_access_view,
    redeem_invite,
    refresh_access_gate_from_gcs,
    user_may_use_paid,
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
    try:
        # WHY: invite/events/redeem must load shared truth on boot (design/69)
        from sentence_reading.llm.access_gate import refresh_access_gate_from_gcs

        refresh_access_gate_from_gcs()
    except Exception:
        pass
    yield


app = FastAPI(
    title="A-sentence-reading",
    version="0.3.31",
    description="One-sentence PDF/DOCX reader with Gemini debone, vision OCR, Cloud TTS.",
    lifespan=_lifespan,
)


class _GcsUidMiddleware(BaseHTTPMiddleware):
    """쿠키 세션 → GCS UID + design/83 login-required gate.

    WHY gate lives here (not a second middleware): Starlette runs the *last*
    added middleware outermost; auth_user must already be set before we decide
    401. EDGE: auth not configured → do not lock the whole app (local mock).
    """

    async def dispatch(self, request: Request, call_next):
        user = parse_session_token(request.cookies.get(COOKIE_NAME))
        request.state.auth_user = user
        set_gcs_uid(user.uid if user else None)
        try:
            # design/83 — identity lock before invite/cost gate (67).
            if (
                login_required_enabled()
                and auth_enabled()
                and user is None
                and not is_login_public_path(request.url.path)
            ):
                path = request.url.path or "/"
                if path.startswith("/api/"):
                    # FAIL-CLOSED: never return a fake-ok body for protected APIs.
                    return JSONResponse(
                        status_code=401,
                        content={
                            "ok": False,
                            "error": "auth_required",
                            "message": "로그인 후 이용해 주세요.",
                        },
                    )
                # Non-API pages (veil, docs, …) → send browser to login shell.
                return RedirectResponse(url="/", status_code=302)
            return await call_next(request)
        finally:
            reset_gcs_uid()


app.add_middleware(_GcsUidMiddleware)


def _request_user(request: Request) -> AuthUser | None:
    user = getattr(request.state, "auth_user", None)
    return user if isinstance(user, AuthUser) else None



def _is_admin_user(user: AuthUser | None) -> bool:
    if user is None:
        return False
    from sentence_reading.llm.usage_meter import is_admin_email

    return is_admin_email(user.email)


def _paid_access_denied(request: Request) -> JSONResponse | None:
    """Return 403/401 if access gate blocks paid APIs; else None."""
    if not access_gate_enabled():
        return None
    user = _request_user(request)
    if user is None:
        if auth_enabled():
            return JSONResponse(
                status_code=401,
                content={
                    "ok": False,
                    "error": "auth_required",
                    "message": "로그인 후 이용해 주세요.",
                },
            )
        return None
    if user_may_use_paid(
        user.uid, email=user.email or "", is_admin=_is_admin_user(user)
    ):
        return None
    view = public_access_view(
        user.uid, email=user.email or "", is_admin=_is_admin_user(user)
    )
    return JSONResponse(
        status_code=403,
        content={
            "ok": False,
            "error": "access_denied",
            "access": view,
            "message": "초대 코드 승인 후 이용할 수 있습니다. (관리자 Allow 필요)",
        },
    )



def _want_shadowing_chunks(request: Request) -> bool:
    """Client opt-in (design/80). Body/query only as boolean flag — never trust user_id."""
    q = (request.query_params.get("shadowing_practice") or "").strip().lower()
    if q in ("1", "true", "yes", "on"):
        return True
    return False


def _want_translate(request: Request) -> bool:
    """Client opt-in for Gemini KO work (design/99).

    Query absent → True (web always-translate compat).
    Explicit 0/false/off → False. Explicit 1/true/on → True.
    """
    if "translate" not in request.query_params:
        return True
    q = (request.query_params.get("translate") or "").strip().lower()
    if q in ("0", "false", "no", "off"):
        return False
    if q in ("1", "true", "yes", "on"):
        return True
    return True


def _ingest_rate_limited(request: Request, action: str) -> JSONResponse | None:
    """
    design/73 — per-uid call-count limit for upload/ingest actions.
    Returns 429 JSON or None. Never trusts body user_id.
    """
    from sentence_reading.llm import ingest_rate_limit as irl

    user = _request_user(request)
    # EDGE: unauthenticated → shared anon bucket (blunt spam without opening uid forge).
    # WHY length≥6: sanitize_uid charset/length invariant.
    uid = user.uid if user is not None else "anon_unauth"
    try:
        irl.check_and_record(uid, action)
    except ValueError as exc:
        code = str(exc)
        if code == "auth_required":
            return JSONResponse(
                status_code=401,
                content={
                    "ok": False,
                    "error": "auth_required",
                    "message": "로그인이 필요합니다.",
                },
            )
        # Product copy: explicit, not advisory / investment language.
        return JSONResponse(
            status_code=429,
            content={
                "ok": False,
                "error": "rate_limited",
                "message": "요청이 너무 많습니다.",
            },
        )
    return None


def _persist_job(job_id: str, job: dict, *, force: bool = False) -> None:
    """design/71 — mirror job to users/{uid}/ingest_jobs when GCS is on."""
    from sentence_reading.llm import ingest_jobs_gcs as ij

    if not ij.should_push_job(job, force=force):
        return
    try:
        ij.save_ingest_job(job_id, job)
    except Exception as exc:  # noqa: BLE001
        # WHY: fail-soft — local poll still works on the worker instance.
        log = __import__("logging").getLogger("sentence_reading.api")
        log.warning("ingest job gcs push failed %s: %s", job_id, exc)


def _job_set(
    job_id: str,
    *,
    percent: int,
    stage: str,
    message: str = "",
    cursor: dict | None = None,
) -> None:
    job = _JOBS.get(job_id)
    if not job or job.get("done"):
        return
    job["percent"] = max(0, min(100, int(percent)))
    job["stage"] = stage
    if message:
        job["message"] = message
    # design/110 — stamp resume envelope (no paper text); skip wired later.
    from sentence_reading.llm import ingest_jobs_gcs as ij

    ij.stamp_checkpoint_on_job(
        job,
        pipeline_version=PIPELINE_VERSION,
        cursor=cursor,
    )
    _persist_job(job_id, job)


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
    _persist_job(job_id, job, force=True)


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
    _persist_job(job_id, job, force=True)
    # WHY: source blob only needed while processing; drop after terminal success.
    owner = str(job.get("owner_uid") or "").strip()
    if owner:
        from sentence_reading.llm import ingest_jobs_gcs as ij

        suf = ".pdf"
        fn = str(job.get("filename") or "").lower()
        if fn.endswith(".docx"):
            suf = ".docx"
        try:
            ij.delete_ingest_upload(job_id, owner_uid=owner, suffix=suf)
        except Exception:  # noqa: BLE001
            pass
        # design/112 — drop mid-stage payload on terminal success.
        try:
            ij.delete_ingest_payload(job_id, owner_uid=owner)
        except Exception:  # noqa: BLE001
            pass


def _mobile_upload_background_enabled() -> bool:
    """design/74 — server kill switch for mobile FG upload notification.

    WHY: share/cloud path must be able to disable client FG/notify without a
    forced APK rollback. Default on; ASR_MOBILE_UPLOAD_BACKGROUND=0 turns off.
    """
    v = (os.environ.get("ASR_MOBILE_UPLOAD_BACKGROUND") or "1").strip().lower()
    return v not in ("0", "false", "off", "no")


def _mobile_upload_interrupt_resume_enabled() -> bool:
    """design/75 — kill switch for stall detect + resume-on-foreground.

    Default on; ASR_MOBILE_UPLOAD_INTERRUPT_RESUME=0 turns off (71 cold resume remains).
    """
    v = (
        os.environ.get("ASR_MOBILE_UPLOAD_INTERRUPT_RESUME") or "1"
    ).strip().lower()
    return v not in ("0", "false", "off", "no")


def _mobile_upload_workmanager_enabled() -> bool:
    """design/76 — kill switch for Android WorkManager process-death resume.

    Default on; ASR_MOBILE_UPLOAD_WORKMANAGER=0 → clients skip enqueue (71/75 remain).
    """
    v = (os.environ.get("ASR_MOBILE_UPLOAD_WORKMANAGER") or "1").strip().lower()
    return v not in ("0", "false", "off", "no")


def _mobile_email_magic_link_enabled() -> bool:
    """design/77 — kill switch for email magic-link login."""
    from sentence_reading.llm.auth_magic_link import magic_link_enabled

    return magic_link_enabled() and email_auth_enabled()


def _email_smtp_configured() -> bool:
    """design/86 — public readiness bit only (no host/user/pass in status)."""
    from sentence_reading.llm.email_smtp import smtp_configured

    return smtp_configured()


def _public_api_base(request: Request) -> str:
    """Stable HTTPS base for email links (prefer ASR_CLOUD_RUN_URL)."""
    env_url = (os.environ.get("ASR_CLOUD_RUN_URL") or "").strip().rstrip("/")
    if env_url:
        return env_url
    return str(request.base_url).rstrip("/")


@app.get("/api/status")
def status(request: Request) -> dict:
    """기동 확인."""
    from sentence_reading.llm.ingest_rate_limit import rate_limit_enabled
    from sentence_reading.llm.ingest_jobs_gcs import (
        ingest_checkpoint_enabled,
        ingest_job_reclaim_enabled,
        ingest_resume_skip_enabled,
    )

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
        "version": "0.3.31",
        # design/83 — identity gate; false only when ASR_LOGIN_REQUIRED=0.
        "login_required": login_required_enabled(),
        "mobile_login_required": login_required_enabled(),
        # design/84 — waiting-only shell when logged in but invite not paid.
        "access_waiting_ux": True,
        "mobile_access_waiting_ux": True,
        # design/85 — web email UI is magic-link only (password UI removed).
        "web_email_magic_link_only": True,
        "access_gate_gcs": True,
        "mobile_upload": True,
        "ingest_job_gcs": True,
        "mobile_upload_resume": True,
        # design/107 — cross-instance reclaim when worker lease expires.
        "ingest_job_reclaim": ingest_job_reclaim_enabled(),
        # design/110 — checkpoint envelope (skip logic later).
        "ingest_checkpoint": ingest_checkpoint_enabled(),
        # design/112 — mid-stage payload skip.
        "ingest_resume_skip": ingest_resume_skip_enabled(),
        # design/113 — chunk build returns pending slices (no gateway 504).
        "shadowing_chunk_budget": True,
        # design/114 — open rejects empty sentence sessions.
        "paper_open_require_sentences": True,
        "ingest_chunked_upload": True,
        # design/73 — mirrors ASR_INGEST_RATE_LIMIT kill switch (False when off).
        "ingest_rate_limit": rate_limit_enabled(),
        # design/74 — clients skip FG/notify when False; upload path unchanged.
        "mobile_upload_background": _mobile_upload_background_enabled(),
        # design/75 — stall honesty + resume-on-app-foreground.
        "mobile_upload_interrupt_resume": _mobile_upload_interrupt_resume_enabled(),
        # design/76 — WorkManager enqueue; false → clients skip (71/75 remain).
        "mobile_upload_workmanager": _mobile_upload_workmanager_enabled(),
        # design/77 — email magic-link; false → clients hide request UI.
        "mobile_email_magic_link": _mobile_email_magic_link_enabled(),
        # design/86 — bool only (host+from present). Never expose SMTP user/pass/host.
        "email_smtp_configured": _email_smtp_configured(),
        # design/79 — shadowing opt-in UI; default off (ASR_SHADOWING_PRACTICE).
        "shadowing_practice": shadowing_practice_enabled(),
        "mobile_shadowing_practice": shadowing_practice_enabled(),
        # design/80 — chunk plans behind same kill; clients show backfill UI when true.
        "shadowing_chunks": shadowing_practice_enabled(),
        "mobile_shadowing_chunks": shadowing_practice_enabled(),
        # design/82 — practice loop UI behind same kill.
        "shadowing_practice_loop": shadowing_practice_enabled(),
        "mobile_shadowing_practice_loop": shadowing_practice_enabled(),
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
        "section_review_keys": True,
        "section_review_crosshair": True,
        "header_overflow": True,
        "guide_header": True,
        "panel_hints_optional": True,
        "compound_figures": False,
        "reading_order": True,
        "github_cd": True,
        "mobile_flutter_scaffold": True,
        "mobile_android_platform": True,
        "mobile_email_auth": True,
        # design/78 — false by default (ASR_EMAIL_PASSWORD unset/0).
        "mobile_email_password": email_password_auth_enabled(),
        "mobile_library": True,
        "mobile_reader": True,
        "mobile_tts": True,
        "mobile_oauth": True,
        "mobile_theme": True,
        "access_gate": True,
        "mobile_access_gate": True,
        "mobile_password_ui": email_password_auth_enabled(),
        "mobile_admin_ui_gate": True,
        "mobile_google_sha_runbook": True,
        "mobile_google_android_oauth": True,
        "mobile_invite_copy_minimal": True,
        "mobile_admin_emails_configured": True,
        "mobile_invite_redeem_e2e": True,
        "mobile_access_session_clear": True,
        "mobile_shell_nav": True,
        "access_gate_enabled": access_gate_enabled(),
        "access_invite_ttl_seconds": invite_ttl_seconds(),
        "access_redeem_max": redeem_max_attempts(),
        "access_redeem_window_sec": redeem_window_seconds(),
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
    st["access"] = public_access_view(
        user.uid if user else None,
        email=(user.email if user else "") or "",
        is_admin=_is_admin_user(user),
    )
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
def auth_kakao_start(
    request: Request, mode: str = "login", mobile: str = "0"
) -> Response:
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
    want_mobile = str(mobile or "0").strip().lower() in ("1", "true", "yes", "on")
    state = issue_oauth_state(m, link_uid=link_uid, mobile=want_mobile)
    url = kakao_authorize_url(
        redirect_uri=_kakao_redirect_uri(request), state=state
    )
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url, status_code=302)


@app.get("/api/auth/kakao/callback")
def auth_kakao_callback(
    request: Request, code: str = "", state: str = "", error: str = ""
) -> Response:
    """Kakao redirect. Web → `/?auth=…`; Flutter mobile state → custom-scheme deep link."""
    from fastapi.responses import RedirectResponse

    parsed = parse_oauth_state(state) if state else None
    is_mobile = bool(parsed and parsed.get("mobile") == "1")

    def _web_err(code_s: str) -> Response:
        return RedirectResponse(
            "/?auth_error=" + urllib.parse.quote(code_s[:80]), status_code=302
        )

    def _mobile_err(code_s: str) -> Response:
        return RedirectResponse(
            mobile_kakao_deep_link(error=code_s), status_code=302
        )

    def _err(code_s: str) -> Response:
        return _mobile_err(code_s) if is_mobile else _web_err(code_s)

    if error:
        return _err("kakao_" + error)
    if not parsed:
        return _err("bad_state")
    try:
        profile = kakao_exchange_code(
            code, redirect_uri=_kakao_redirect_uri(request)
        )
        subject = str(profile["subject"])
        if parsed["mode"] == "link":
            uid = parsed.get("link_uid") or ""
            if not uid:
                return _err("link_uid")
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
            return _err("conflict")
        return _err(err[:80])

    token = issue_session_token(user)
    if is_mobile:
        # WHY: Custom-tab cookie is not visible to Flutter; pass signed session in query.
        resp = RedirectResponse(
            mobile_kakao_deep_link(session=token, auth=msg), status_code=302
        )
    else:
        resp = RedirectResponse("/?auth=" + msg, status_code=302)
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


@app.post("/api/auth/email/register")
async def auth_email_register(payload: dict = Body(...)) -> JSONResponse:
    if not email_auth_enabled():
        return JSONResponse(
            status_code=503,
            content={"ok": False, "error": "email_disabled", "message": "이메일 가입이 꺼져 있습니다."},
        )
    if not email_password_auth_enabled():
        # design/78 — fail-closed: do not collect new password hashes by default.
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": "email_password_disabled",
                "message": "이메일 비밀번호 가입이 꺼져 있습니다. 로그인 링크로 들어가세요.",
            },
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
    if not email_password_auth_enabled():
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": "email_password_disabled",
                "message": "이메일 비밀번호 로그인이 꺼져 있습니다. 로그인 링크로 들어가세요.",
            },
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


def _user_from_magic_email(em: str) -> AuthUser:
    """Redeem path: existing email user or passwordless create (design/77)."""
    return resolve_or_create("email", em, email=em, name="", password=None)


@app.post("/api/auth/email/magic/request")
async def auth_email_magic_request(
    request: Request, payload: dict = Body(...)
) -> JSONResponse:
    """Mint + SMTP send magic login link. Fail-closed if SMTP/kill missing."""
    from sentence_reading.llm.auth_magic_link import mint_magic_token
    from sentence_reading.llm.email_smtp import send_magic_link_email, smtp_configured

    if not _mobile_email_magic_link_enabled():
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": "magic_disabled",
                "message": "이메일 로그인 링크가 꺼져 있습니다.",
            },
        )
    if not smtp_configured():
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": "smtp_not_configured",
                "message": "이메일 발송 설정이 없어 링크를 보낼 수 없습니다.",
            },
        )
    email = str(payload.get("email") or "") if isinstance(payload, dict) else ""
    # design/85 — android/app mail must deep-link; web omits mobile=1 (browser cookie).
    client_hint = ""
    if isinstance(payload, dict):
        client_hint = str(payload.get("client") or "").strip().lower()
    for_mobile = client_hint in ("android", "mobile", "app")
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
    try:
        minted = mint_magic_token(em)
    except ValueError as exc:
        code = str(exc)
        if code == "rate_limited":
            return JSONResponse(
                status_code=429,
                content={
                    "ok": False,
                    "error": "rate_limited",
                    "message": "요청이 너무 많습니다. 잠시 후 다시 시도하세요.",
                },
            )
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": code, "message": "요청을 처리할 수 없습니다."},
        )
    open_url = (
        _public_api_base(request)
        + "/api/auth/email/magic/open?t="
        + urllib.parse.quote(minted["token"], safe="")
    )
    if for_mobile:
        open_url += "&mobile=1"
    try:
        send_magic_link_email(to_email=em, open_url=open_url)
    except ValueError as exc:
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": str(exc),
                "message": "이메일 발송 설정이 없어 링크를 보낼 수 없습니다.",
            },
        )
    except RuntimeError:
        return JSONResponse(
            status_code=502,
            content={
                "ok": False,
                "error": "smtp_send_failed",
                "message": "이메일을 보내지 못했습니다. 잠시 후 다시 시도하세요.",
            },
        )
    # WHY: same success copy whether or not the address already has an account.
    return JSONResponse(
        {
            "ok": True,
            "message": "로그인 링크를 이메일로 보냈습니다. 메일함에서 열어 주세요.",
        }
    )


@app.get("/api/auth/email/magic/open")
def auth_email_magic_open(
    request: Request, t: str = "", mobile: str = ""
) -> Response:
    """Redeem once → set session cookie; web lands on `/`, Android may deep-link.

    design/85 — browser click must establish web session (product).
    EDGE: ``mobile=1`` keeps Android deep-link for app mail clients (77).
    """
    raw = (t or "").strip()
    want_mobile = (mobile or "").strip().lower() in ("1", "true", "yes", "android", "app")
    try:
        from sentence_reading.llm.auth_magic_link import redeem_magic_token

        em = redeem_magic_token(raw)
        user = _user_from_magic_email(em)
        token = issue_session_token(user)
        if want_mobile:
            # WHY: Flutter cold-start reads asr_session from custom-scheme query.
            resp = RedirectResponse(
                url=mobile_magic_deep_link(session=token, auth="magic"),
                status_code=302,
            )
        else:
            # design/85 — web session for browser mail opens.
            resp = RedirectResponse(url="/?auth=logged_in", status_code=302)
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
    except ValueError as exc:
        code = str(exc)[:80]
        if want_mobile:
            return RedirectResponse(
                url=mobile_magic_deep_link(error=code), status_code=302
            )
        # FAIL-CLOSED: do not pretend login; surface safe error code only.
        return RedirectResponse(
            url="/?auth_error=" + urllib.parse.quote(code, safe=""),
            status_code=302,
        )


@app.post("/api/auth/email/magic/admin/mint")
async def auth_email_magic_admin_mint(
    request: Request, payload: dict = Body(None)
) -> JSONResponse:
    """Admin-only: return one open URL (no SMTP). For device E2E / support."""
    from sentence_reading.llm.auth_magic_link import mint_magic_token

    user = _request_user(request)
    if user is None or not _is_admin_user(user):
        return JSONResponse(
            status_code=403,
            content={
                "ok": False,
                "error": "admin_required",
                "message": "관리자만 로그인 링크를 발급할 수 있습니다.",
            },
        )
    if not _mobile_email_magic_link_enabled():
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": "magic_disabled",
                "message": "이메일 로그인 링크가 꺼져 있습니다.",
            },
        )
    email = ""
    client_hint = "android"  # WHY: admin mint historically for device E2E deep-link.
    if isinstance(payload, dict):
        email = str(payload.get("email") or "")
        if payload.get("client") is not None:
            client_hint = str(payload.get("client") or "").strip().lower()
    # EDGE: client=web → browser cookie path (design/85); else keep mobile deep-link.
    for_mobile = client_hint not in ("web", "browser")
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
    try:
        minted = mint_magic_token(em)
    except ValueError as exc:
        code = str(exc)
        status = 429 if code == "rate_limited" else 400
        return JSONResponse(
            status_code=status,
            content={
                "ok": False,
                "error": code,
                "message": "요청을 처리할 수 없습니다.",
            },
        )
    open_url = (
        _public_api_base(request)
        + "/api/auth/email/magic/open?t="
        + urllib.parse.quote(minted["token"], safe="")
    )
    if for_mobile:
        open_url += "&mobile=1"
    return JSONResponse(
        {
            "ok": True,
            "open_url": open_url,
            "expires_at": minted["expires_at"],
            "ttl_seconds": minted["ttl_seconds"],
            "message": "이 URL은 지금만 표시됩니다. 메일/채팅에 장시간 보관하지 마세요.",
        }
    )


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
    if not email_password_auth_enabled():
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": "email_password_disabled",
                "message": "이메일 비밀번호 연결이 꺼져 있습니다.",
            },
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
async def stt_recognize(request: Request, file: UploadFile = File(...),
    expected: str = Form(""),
) -> dict:
    """연습 오디오 → 영어 전사 (+선택 compare). 점수 없음 (design/38)."""
    denied = _paid_access_denied(request)
    if denied is not None:
        return denied
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
async def translate_sentence(request: Request, payload: dict = Body(...)) -> dict:
    """영→한 번역 (design/35 simple · design/36 pipeline 기본)."""
    denied = _paid_access_denied(request)
    if denied is not None:
        return denied
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




@app.get("/api/access/status")
def access_status(request: Request) -> dict:
    user = _request_user(request)
    # WHY: Settings「새로고침」must see Allow minted on another instance (design/69)
    if user is not None:
        try:
            refresh_access_gate_from_gcs()
        except Exception:
            pass
    return {
        "ok": True,
        **public_access_view(
            user.uid if user else None,
            email=(user.email if user else "") or "",
            is_admin=_is_admin_user(user),
        ),
    }


@app.post("/api/access/invite")
async def access_invite(request: Request, payload: dict = Body(...)) -> JSONResponse:
    user = _request_user(request)
    if user is None:
        return JSONResponse(
            status_code=401,
            content={
                "ok": False,
                "error": "auth_required",
                "message": "로그인 후 초대 코드를 입력하세요.",
            },
        )
    code = str(payload.get("code") or "") if isinstance(payload, dict) else ""
    try:
        view = redeem_invite(
            user.uid, code, email=user.email or "", name=user.name or ""
        )
    except ValueError as exc:
        code_e = str(exc)
        messages = {
            "gate_disabled": "액세스 게이트가 꺼져 있습니다.",
            "empty_code": "초대 코드를 입력하세요.",
            "bad_code": "초대 코드가 올바르지 않습니다.",
            "code_used": "이미 사용된 초대 코드입니다.",
            "code_revoked": "폐기된 초대 코드입니다.",
            "code_expired": "만료된 초대 코드입니다. 관리자에게 새 코드를 요청하세요.",
            "rate_limited": "시도가 너무 많습니다. 잠시 후 다시 시도하세요.",
            "auth_required": "로그인이 필요합니다.",
        }
        status = 400
        if code_e == "bad_code":
            status = 403
        if code_e == "gate_disabled":
            status = 503
        if code_e in ("code_used", "code_revoked", "code_expired"):
            status = 409
        if code_e == "rate_limited":
            status = 429
        return JSONResponse(
            status_code=status,
            content={
                "ok": False,
                "error": code_e,
                "message": messages.get(code_e, code_e),
            },
        )
    return JSONResponse(
        {
            "ok": True,
            "access": view,
            "message": "pending" if view.get("status") == "pending" else "ok",
        }
    )


@app.get("/api/access/admin/pending")
def access_admin_pending(request: Request) -> JSONResponse:
    user = _request_user(request)
    if user is None or not _is_admin_user(user):
        return JSONResponse(
            status_code=403,
            content={
                "ok": False,
                "error": "admin_required",
                "message": "관리자만 볼 수 있습니다.",
            },
        )
    return JSONResponse({"ok": True, "pending": list_pending()})


@app.get("/api/access/admin/notifications")
def access_admin_notifications(request: Request, limit: int = 50) -> JSONResponse:
    user = _request_user(request)
    if user is None or not _is_admin_user(user):
        return JSONResponse(
            status_code=403,
            content={
                "ok": False,
                "error": "admin_required",
                "message": "관리자만 볼 수 있습니다.",
            },
        )
    try:
        lim = int(limit)
    except (TypeError, ValueError):
        lim = 50
    return JSONResponse({"ok": True, "events": list_events(limit=lim)})



@app.post("/api/access/admin/mint")
async def access_admin_mint(request: Request, payload: dict = Body(None)) -> JSONResponse:
    """Mint one OTP-style invite (XXXX-XXXX). Plaintext returned once."""
    user = _request_user(request)
    if user is None or not _is_admin_user(user):
        return JSONResponse(
            status_code=403,
            content={
                "ok": False,
                "error": "admin_required",
                "message": "관리자만 초대 코드를 발급할 수 있습니다.",
            },
        )
    note = ""
    if isinstance(payload, dict):
        note = str(payload.get("note") or "")
    try:
        minted = mint_invite_code(
            admin_uid=user.uid, admin_email=user.email or "", note=note
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": str(exc), "message": str(exc)},
        )
    return JSONResponse(
        {
            "ok": True,
            "code": minted["code"],
            "created_at": minted["created_at"],
            "expires_at": minted.get("expires_at"),
            "ttl_seconds": minted.get("ttl_seconds"),
            "single_use": True,
            "message": "이 코드는 지금만 표시됩니다. 만료 전·1회만 사용하세요.",
        }
    )


@app.get("/api/access/admin/invites")
def access_admin_invites(request: Request, limit: int = 20) -> JSONResponse:
    user = _request_user(request)
    if user is None or not _is_admin_user(user):
        return JSONResponse(
            status_code=403,
            content={
                "ok": False,
                "error": "admin_required",
                "message": "관리자만 볼 수 있습니다.",
            },
        )
    try:
        lim = int(limit)
    except (TypeError, ValueError):
        lim = 20
    return JSONResponse({"ok": True, "open": list_open_invite_meta(limit=lim)})


@app.post("/api/access/admin/decide")
async def access_admin_decide(
    request: Request, payload: dict = Body(...)
) -> JSONResponse:
    user = _request_user(request)
    if user is None or not _is_admin_user(user):
        return JSONResponse(
            status_code=403,
            content={
                "ok": False,
                "error": "admin_required",
                "message": "관리자만 처리할 수 있습니다.",
            },
        )
    if not isinstance(payload, dict):
        payload = {}
    uid = str(payload.get("uid") or "")
    decision = str(payload.get("decision") or payload.get("action") or "")
    note = str(payload.get("note") or "")
    try:
        view = decide_access(
            uid,
            decision,
            admin_uid=user.uid,
            admin_email=user.email or "",
            note=note,
        )
    except ValueError as exc:
        code_e = str(exc)
        status = 404 if code_e == "user_not_found" else 400
        return JSONResponse(
            status_code=status,
            content={"ok": False, "error": code_e, "message": code_e},
        )
    return JSONResponse({"ok": True, "access": view})


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
async def tts_synthesize(request: Request, payload: dict = Body(...)) -> Response:
    """현재 문장 plain text → MP3."""
    denied = _paid_access_denied(request)
    if denied is not None:
        return denied
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
async def cache_open(request: Request, cache_id: str) -> JSONResponse:
    """보관본을 즉시 세션으로 연다. 로컬 miss 시 GCS pull · KO 없으면 번역 백필."""
    denied = _paid_access_denied(request)
    if denied is not None:
        return denied
    try:
        from sentence_reading.llm.papers_gcs import (
            ensure_paper_local,
            paper_open_require_sentences,
        )

        loaded = load_cached_session(cache_id)
        # design/114 — empty local session is not a hit; force GCS refresh.
        need_pull = loaded is None or (
            paper_open_require_sentences() and not loaded[0].sentences
        )
        if need_pull:
            try:
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
        # design/114 — never return ok with title-only / zero sentences.
        if paper_open_require_sentences() and not session.sentences:
            return JSONResponse(
                status_code=422,
                content={
                    "ok": False,
                    "error": "empty_session",
                    "message": "보관본에 문장이 없습니다. 원본이 있으면 재분석하거나 PDF를 다시 올려 주세요.",
                },
            )
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
        # design/99 — mobile may pass translate=0 to skip KO backfill until opted in.
        bf_warn: list[str] = []
        if _want_translate(request):
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
    except Exception as exc:  # noqa: BLE001
        # design/111 — never leave clients with bare HTML 500 / empty body.
        # EDGE: do not echo paths, stacks, or paper titles.
        log = __import__("logging").getLogger("sentence_reading.api")
        log.warning("cache_open failed: %s", type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "cache_open_failed",
                "message": "논문을 열지 못했습니다. 잠시 후 다시 시도해 주세요.",
            },
        )


@app.post("/api/cache/papers/{cache_id}/reanalyze")
async def cache_reanalyze(request: Request, cache_id: str) -> JSONResponse:
    """보관된 원본(source.pdf|docx)으로 파이프라인 재실행. 같은 cache_id 유지."""
    denied = _paid_access_denied(request)
    if denied is not None:
        return denied
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
    user = _request_user(request)
    owner_uid = user.uid if user is not None else ""
    from sentence_reading.llm import ingest_jobs_gcs as ij

    content_hash = await asyncio.to_thread(_file_sha256, tmp_path)
    _JOBS[job_id] = {
        "percent": 1,
        "stage": "queued",
        "message": "재분석 시작",
        "done": False,
        "error": None,
        "result": None,
        "owner_uid": owner_uid,
        "content_hash": content_hash or "",
        "filename": ij.safe_filename(filename),
    }
    if owner_uid:
        _persist_job(job_id, _JOBS[job_id], force=True)
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
def cache_delete(request: Request, cache_id: str) -> JSONResponse:
    """보관(증류)본 삭제 — 로컬·GCS 논문 + 같은 uid 사용자 기록 (design/102)."""
    denied = _paid_access_denied(request)
    if denied is not None:
        return denied
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
async def cache_delete_by_meta(request: Request, payload: dict = Body(...)) -> JSONResponse:
    """cache_id 없거나 모를 때 title+source 로 삭제."""
    denied = _paid_access_denied(request)
    if denied is not None:
        return denied
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


@app.patch("/api/session/{session_id}/cursor")
async def session_patch_cursor(session_id: str, payload: dict = Body(...)) -> JSONResponse:
    """Update sentence/figure cursors independently (design/04 · design/63).

    INVARIANT: only the keys present in the body are applied — never force both.
    """
    if session_id == "ses_mock":
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": "mock_readonly",
                "message": "mock 세션 커서는 저장하지 않습니다.",
            },
        )
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
    body = payload if isinstance(payload, dict) else {}
    # EDGE: ignore unknown keys; only apply provided indices
    if "sentence_index" in body:
        try:
            session.sentence_index = int(body.get("sentence_index"))
        except (TypeError, ValueError):
            return JSONResponse(
                status_code=400,
                content={
                    "ok": False,
                    "error": "bad_sentence_index",
                    "message": "sentence_index 가 올바르지 않습니다.",
                },
            )
    if "figure_index" in body:
        try:
            session.figure_index = int(body.get("figure_index"))
        except (TypeError, ValueError):
            return JSONResponse(
                status_code=400,
                content={
                    "ok": False,
                    "error": "bad_figure_index",
                    "message": "figure_index 가 올바르지 않습니다.",
                },
            )
    session.clamp_indices()
    data = session.to_public_dict()
    data["ok"] = True
    data["session_id"] = session_id
    return JSONResponse(data)


async def _ingest_lease_heartbeat(job_id: str) -> None:
    """design/107 — keep lease fresh while this instance runs the worker."""
    from sentence_reading.llm import ingest_jobs_gcs as ij

    interval = ij.heartbeat_interval_seconds()
    while True:
        await asyncio.sleep(interval)
        job = _JOBS.get(job_id)
        if not job or job.get("done") or job.get("error"):
            return
        if not job.get("_local_running"):
            return
        ij.stamp_lease(job, token=str(job.get("lease_token") or "") or None)
        _persist_job(job_id, job, force=True)


async def _reclaim_ingest_job_from_gcs(job_id: str, owner_uid: str) -> bool:
    """
    Restart processing from GCS upload blob when the prior worker lease expired.
    WHY: root fix for orphaned 12% jobs — not a fake percent bump.
    EDGE: no blob → False (fail-closed, no empty success).
    """
    from sentence_reading.llm import ingest_jobs_gcs as ij

    if not ij.ingest_job_reclaim_enabled():
        return False
    existing = _JOBS.get(job_id)
    # WHY: this instance already has an active worker — do not double-start.
    if existing is not None and existing.get("_local_running"):
        return False
    token = ij.try_claim_lease(job_id, owner_uid=owner_uid)
    if not token:
        return False
    raw = ij.load_ingest_upload(job_id, owner_uid=owner_uid, suffix=".pdf")
    kind = "pdf"
    suffix = ".pdf"
    if not raw:
        raw = ij.load_ingest_upload(job_id, owner_uid=owner_uid, suffix=".docx")
        kind = "docx"
        suffix = ".docx"
    if not raw:
        # EDGE: lease claimed but bytes gone — leave job as-is; next poll can retry.
        return False
    meta = ij.load_ingest_job(job_id, owner_uid=owner_uid) or {}
    filename = ij.safe_filename(str(meta.get("filename") or f"reclaim{suffix}"))
    content_hash = str(meta.get("content_hash") or "").strip() or None
    # design/110·112 — accept/discard checkpoint; load payload for skip when enabled.
    cp_raw = meta.get("checkpoint")
    cp_ok, cp_reason = ij.checkpoint_is_valid(
        cp_raw,
        content_hash=content_hash or "",
        pipeline_version=PIPELINE_VERSION,
    )
    kept_cp = cp_raw if cp_ok and isinstance(cp_raw, dict) else None
    resume_payload = None
    if kept_cp is not None and ij.ingest_resume_skip_enabled():
        loaded_pl = ij.load_ingest_payload(job_id, owner_uid=owner_uid)
        pl_ok, pl_reason = ij.payload_is_valid(
            loaded_pl,
            content_hash=content_hash or "",
            pipeline_version=PIPELINE_VERSION,
        )
        if pl_ok:
            resume_payload = loaded_pl
            reclaim_msg = ij.checkpoint_resume_message(kept_cp)
            cp_reason = "ok"
        else:
            # WHY: envelope without usable payload → honest full restart.
            kept_cp = None
            reclaim_msg = "처리 다시 시작"
            cp_reason = pl_reason
            try:
                ij.delete_ingest_payload(job_id, owner_uid=owner_uid)
            except Exception:  # noqa: BLE001
                pass
    elif kept_cp is not None:
        reclaim_msg = ij.checkpoint_resume_message(kept_cp)
    else:
        reclaim_msg = "처리 다시 시작"
        kept_cp = None
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(raw)
        tmp_path = Path(tmp.name)
    seed_stage = str(
        (resume_payload or {}).get("completed")
        or (kept_cp or {}).get("stage")
        or meta.get("stage")
        or "queued"
    )
    seed_pct = max(
        ij.stage_percent_floor(seed_stage),
        int(meta.get("percent") or 1),
    )
    # design/112 — keep partial result only when translating from ready payload.
    keep_result = None
    if isinstance(meta.get("result"), dict) and str(
        (resume_payload or {}).get("completed") or ""
    ) in ("ready", "translate"):
        keep_result = meta.get("result")
    job = {
        "percent": seed_pct,
        "stage": seed_stage if seed_stage != "queued" else str(meta.get("stage") or "queued"),
        "message": reclaim_msg,
        "done": False,
        "error": None,
        "result": keep_result,
        "owner_uid": owner_uid,
        "content_hash": content_hash or "",
        "filename": filename,
        "want_shadowing_chunks": bool(meta.get("want_shadowing_chunks", False)),
        "want_translate": bool(meta.get("want_translate", True)),
        "lease_token": token,
        "lease_until": meta.get("lease_until"),
        "checkpoint": kept_cp,
        "_checkpoint_reclaim": cp_reason,
        "_resume_payload": resume_payload,
        "_local_running": True,
    }
    ij.stamp_lease(job, token=token)
    _JOBS[job_id] = job
    _persist_job(job_id, job, force=True)
    asyncio.create_task(
        _run_ingest_job(
            job_id,
            tmp_path,
            filename,
            kind,
            content_hash=content_hash,
        )
    )
    return True


@app.get("/api/ingest/jobs/{job_id}")
async def ingest_job_status(request: Request, job_id: str) -> JSONResponse:
    """업로드·정제 진행률 폴링 (design/71 — memory then owner-scoped GCS)."""
    from sentence_reading.llm import ingest_jobs_gcs as ij

    jid = (job_id or "").strip()
    # EDGE: block path tricks (../); allow job_* memory keys used by tests.
    if not jid.startswith("job_") or "/" in jid or "\\" in jid or ".." in jid:
        return JSONResponse(
            status_code=404,
            content={
                "ok": False,
                "error": "job_not_found",
                "message": "작업을 찾을 수 없습니다.",
            },
        )

    user = _request_user(request)
    job = _JOBS.get(jid)
    if user is not None:
        # WHY: other Cloud Run instance — shared truth is users/{uid}/ingest_jobs.
        # design/106: also re-load when local cache is non-terminal so a stale
        # 12% quality snapshot cannot pin the poll forever after GCS advances.
        loaded = ij.load_ingest_job(jid, owner_uid=user.uid)
        if loaded is not None:
            if job is None:
                job = loaded
                _JOBS[jid] = dict(loaded)
            elif not job.get("done") and not job.get("error"):
                gcs_p = int(loaded.get("percent") or 0)
                loc_p = int(job.get("percent") or 0)
                if (
                    loaded.get("done")
                    or loaded.get("error")
                    or gcs_p > loc_p
                    or (
                        gcs_p == loc_p
                        and str(loaded.get("stage") or "")
                        != str(job.get("stage") or "")
                    )
                    or (
                        gcs_p == loc_p
                        and str(loaded.get("message") or "")
                        != str(job.get("message") or "")
                    )
                    or (
                        # design/107 — pick up fresher lease from GCS
                        str(loaded.get("lease_until") or "")
                        != str(job.get("lease_until") or "")
                    )
                ):
                    for key in (
                        "percent",
                        "stage",
                        "message",
                        "done",
                        "error",
                        "result",
                        "content_hash",
                        "filename",
                        "lease_until",
                        "lease_token",
                    ):
                        if key in loaded:
                            job[key] = loaded[key]

    if job is None:
        return JSONResponse(
            status_code=404,
            content={
                "ok": False,
                "error": "job_not_found",
                "message": "작업을 찾을 수 없습니다.",
            },
        )

    owner = str(job.get("owner_uid") or "").strip()
    # WHY: multi-user — never leak another account’s job by id guessing.
    if owner:
        if user is None:
            return JSONResponse(
                status_code=401,
                content={
                    "ok": False,
                    "error": "auth_required",
                    "message": "로그인이 필요합니다.",
                },
            )
        if user.uid != owner:
            return JSONResponse(
                status_code=404,
                content={
                    "ok": False,
                    "error": "job_not_found",
                    "message": "작업을 찾을 수 없습니다.",
                },
            )
        # design/107 — owner poll may restart an abandoned worker (lease expired).
        if (
            not job.get("done")
            and not job.get("error")
            and not job.get("_local_running")
            and ij.ingest_job_reclaim_enabled()
            and ij.lease_expired(job)
        ):
            await _reclaim_ingest_job_from_gcs(jid, owner)
            job = _JOBS.get(jid) or job

    return JSONResponse(ij.public_job_view(jid, job))


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
    from sentence_reading.llm import ingest_jobs_gcs as ij

    warnings: list[str] = []
    job = _JOBS.get(job_id)
    if job is not None:
        job["_local_running"] = True
        ij.stamp_lease(job)
        _persist_job(job_id, job, force=True)
    heartbeat = asyncio.create_task(_ingest_lease_heartbeat(job_id))
    try:
        await _run_ingest_job_body(
            job_id,
            tmp_path,
            filename,
            kind,
            skip_cache=skip_cache,
            content_hash=content_hash,
            warnings=warnings,
        )
    finally:
        heartbeat.cancel()
        try:
            await heartbeat
        except asyncio.CancelledError:
            pass
        fin = _JOBS.get(job_id)
        if fin is not None:
            fin["_local_running"] = False


async def _run_ingest_job_body(
    job_id: str,
    tmp_path: Path,
    filename: str,
    kind: str,
    *,
    skip_cache: bool = False,
    content_hash: str | None = None,
    warnings: list[str],
) -> None:
    try:
        from sentence_reading.llm import ingest_jobs_gcs as ij
        from sentence_reading.llm import ingest_resume_payload as irp

        label = "PDF" if kind == "pdf" else "Word"
        if not content_hash:
            content_hash = await asyncio.to_thread(_file_sha256, tmp_path)

        job0 = _JOBS.get(job_id) or {}
        resume_pl = job0.get("_resume_payload")
        if not isinstance(resume_pl, dict):
            resume_pl = None
        # design/112 — if reclaim handed a payload, skip prior Gemini stages.
        resume_completed = str((resume_pl or {}).get("completed") or "")
        skip_vision = resume_completed in {
            "vision",
            "debone",
            "ready",
            "translate",
        }
        skip_debone = resume_completed in {"debone", "ready", "translate"}
        jump_ready = resume_completed in {"ready", "translate"}
        # WHY: completed=translate means KO already in payload — skip Gemini enrich.
        skip_translate = resume_completed == "translate"
        vision_resume = None
        if resume_completed == "vision_partial" and isinstance(resume_pl, dict):
            vision_resume = {
                "decision": resume_pl.get("decision") or {},
                "vision_indices": resume_pl.get("vision_indices") or [],
                "vision_done": int(resume_pl.get("vision_done") or 0),
                "pages": resume_pl.get("pages"),
                "warnings": resume_pl.get("warnings") or [],
            }

        def _owner() -> str:
            return str((_JOBS.get(job_id) or {}).get("owner_uid") or "")

        def _save_payload(doc: dict) -> None:
            owner = _owner()
            if not owner or not ij.ingest_resume_skip_enabled():
                return
            doc = dict(doc)
            doc.setdefault("job_id", job_id)
            doc.setdefault("owner_uid", owner)
            doc.setdefault("content_hash", str(content_hash or ""))
            doc.setdefault("pipeline_version", PIPELINE_VERSION)
            doc["updated_at"] = irp.utc_now_iso()
            ok = ij.save_ingest_payload(job_id, doc, owner_uid=owner)
            if not ok:
                return
            j = _JOBS.get(job_id)
            if j is not None:
                # WHY: envelope points at server-minted relative key only.
                pref = f"{job_id}.json"
                cur = j.get("checkpoint") if isinstance(j.get("checkpoint"), dict) else {}
                j["checkpoint"] = ij.build_checkpoint(
                    stage=str(j.get("stage") or doc.get("completed") or "vision"),
                    content_hash=str(content_hash or ""),
                    pipeline_version=PIPELINE_VERSION,
                    cursor=(cur or {}).get("cursor")
                    if isinstance((cur or {}).get("cursor"), dict)
                    else None,
                    payload_ref=pref,
                )
                _persist_job(job_id, j, force=True)

        def _discard_resume(reason: str) -> None:
            # Product: resume failure → discard + continue as full restart.
            j = _JOBS.get(job_id)
            if j is not None:
                j.pop("_resume_payload", None)
                j["checkpoint"] = None
            owner = _owner()
            if owner:
                try:
                    ij.delete_ingest_payload(job_id, owner_uid=owner)
                except Exception:  # noqa: BLE001
                    pass
            _ = reason  # machine reason kept out of user-facing copy

        if resume_pl and (
            skip_vision or vision_resume is not None
        ) and isinstance(resume_pl.get("pages"), list):
            # WHY: vision_partial also reuses pages so we do not re-extract then overwrite.
            pdf_pages = [str(p or "") for p in resume_pl["pages"]]
            text = str(resume_pl.get("text") or pdf_extract.join_page_texts(pdf_pages))
            warnings.extend(str(w) for w in (resume_pl.get("warnings") or []) if w)
            floor = ij.stage_percent_floor(
                "vision" if vision_resume is not None else "vision"
            )
            _job_set(
                job_id,
                percent=max(floor, int((_JOBS.get(job_id) or {}).get("percent") or floor)),
                stage="vision",
                message=str(
                    (_JOBS.get(job_id) or {}).get("message")
                    or (
                        "비전 이어받는 중"
                        if vision_resume is not None
                        else "이어받는 중"
                    )
                ),
            )
        else:
            _job_set(job_id, percent=5, stage="extract", message=f"{label} 읽는 중")
            pdf_pages = None
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
        if not skip_cache and not jump_ready:
            _job_set(job_id, percent=10, stage="cache", message="제목으로 보관본 찾는 중")
            cached = await asyncio.to_thread(_try_cache_hit, text, kind)
            if cached is not None:
                session, info, hit = cached
                await asyncio.to_thread(
                    attach_source_file, str(hit["id"]), tmp_path, source=kind
                )
                want_tr = bool(
                    (_JOBS.get(job_id) or {}).get("want_translate", True)
                )
                bf_warn: list[str] = []
                if want_tr:
                    session, bf_warn = await _backfill_cached_translations(
                        job_id,
                        session,
                        kind=kind,
                        source_path=tmp_path,
                        content_hash=content_hash,
                    )
                else:
                    bf_warn = ["translate_skipped_opt_out"]
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
        if kind == "pdf" and pdf_pages is not None and not skip_vision:

            def on_recover(
                stage: str, done: int, total: int, message: str
            ) -> None:
                if stage == "quality":
                    pct = 12 + (8 if total and done >= total else 4)
                elif stage == "vision" and total > 0:
                    # Seed near resume floor when mid-vision reclaim.
                    base = 20
                    if vision_resume is not None:
                        base = max(
                            20,
                            int((_JOBS.get(job_id) or {}).get("percent") or 20),
                        )
                    pct = base + int(18 * (done / total))
                    pct = min(38, pct)
                else:
                    pct = 18
                cur = {"done": done, "total": total} if total > 0 else None
                _job_set(
                    job_id,
                    percent=pct,
                    stage=stage,
                    message=message,
                    cursor=cur,
                )

            def on_vision_checkpoint(snap: dict) -> None:
                # Persist vision_partial under owner only — never on public poll.
                dec = snap.get("decision")
                _save_payload(
                    {
                        **irp.base_payload(
                            job_id=job_id,
                            owner_uid=_owner(),
                            content_hash=str(content_hash or ""),
                            completed="vision_partial",
                        ),
                        "pages": list(snap.get("pages") or []),
                        "text": pdf_extract.join_page_texts(
                            list(snap.get("pages") or [])
                        ),
                        "warnings": list(snap.get("warnings") or []),
                        "decision": irp.decision_to_dict(dec),
                        "vision_indices": list(snap.get("vision_indices") or []),
                        "vision_done": int(snap.get("vision_done") or 0),
                    }
                )

            if vision_resume is not None:
                _job_set(
                    job_id,
                    percent=max(20, int((_JOBS.get(job_id) or {}).get("percent") or 20)),
                    stage="vision",
                    message="비전 이어받는 중",
                )
            else:
                _job_set(job_id, percent=12, stage="quality", message="추출 품질 보는 중")
            recovered = await asyncio.to_thread(
                recover_pdf_text,
                tmp_path,
                pdf_pages,
                on_progress=on_recover,
                resume=vision_resume,
                on_checkpoint=on_vision_checkpoint,
            )
            text = recovered.text
            pdf_pages = recovered.pages
            warnings.extend(recovered.warnings)
            # design/112 — durable vision boundary for later reclaim skip.
            _save_payload(
                {
                    **irp.base_payload(
                        job_id=job_id,
                        owner_uid=_owner(),
                        content_hash=str(content_hash or ""),
                        completed="vision",
                    ),
                    "pages": list(pdf_pages or []),
                    "text": text,
                    "warnings": list(warnings),
                    "vision_pages": list(recovered.vision_pages or []),
                    "decision": irp.decision_to_dict(recovered.decision),
                    "vision_indices": list(recovered.vision_pages or []),
                    "vision_done": len(recovered.vision_pages or []),
                }
            )
            if recovered.vision_pages and not skip_cache:
                # 복구 후 제목이 보이면 보관본 재사용
                _job_set(job_id, percent=40, stage="cache", message="복구 후 보관본 확인")
                cached = await asyncio.to_thread(_try_cache_hit, text, kind)
                if cached is not None:
                    session, info, hit = cached
                    await asyncio.to_thread(
                        attach_source_file, str(hit["id"]), tmp_path, source=kind
                    )
                    want_tr = bool(
                        (_JOBS.get(job_id) or {}).get("want_translate", True)
                    )
                    bf_warn = []
                    if want_tr:
                        session, bf_warn = await _backfill_cached_translations(
                            job_id,
                            session,
                            kind=kind,
                            source_path=tmp_path,
                            content_hash=content_hash,
                        )
                    else:
                        bf_warn = ["translate_skipped_opt_out"]
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
        sentences: list = []
        references: list = []
        title = Path(filename).stem or "Untitled"
        digests: dict = {}
        resumed_debone = False
        if skip_debone and isinstance(resume_pl, dict) and resume_pl.get("sentences"):
            try:
                restored = []
                for row in resume_pl.get("sentences") or []:
                    s = irp.sentence_from_dict(row) if isinstance(row, dict) else None
                    if s is not None:
                        restored.append(s)
                if not restored:
                    raise ValueError("empty_sentences")
                sentences = restored
                debone_ok = bool(resume_pl.get("debone_ok"))
                title = str(resume_pl.get("title") or title)
                references = list(resume_pl.get("references") or [])
                digests = dict(resume_pl.get("translate_digests") or {})
                warnings.extend(
                    str(w) for w in (resume_pl.get("warnings") or []) if w
                )
                resumed_debone = True
                floor = ij.stage_percent_floor("debone")
                _job_set(
                    job_id,
                    percent=max(
                        floor, int((_JOBS.get(job_id) or {}).get("percent") or floor)
                    ),
                    stage="debone",
                    message=str(
                        (_JOBS.get(job_id) or {}).get("message") or "다듬기 이어받음"
                    ),
                )
            except Exception:  # noqa: BLE001
                _discard_resume("debone_load")
                skip_debone = False
                jump_ready = False
                skip_translate = False
                resumed_debone = False
                sentences = []

        if not resumed_debone:
            if gemini_available() and text.strip():

                def on_progress(done: int, total: int) -> None:
                    if total <= 0:
                        return
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
                        cursor={"done": done, "total": total},
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
                    text_ko=getattr(s, "text_ko", "") or "",
                    text_ko_stage=getattr(s, "text_ko_stage", "") or "",
                )
                for s in sentences
            ]

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
            digests = {}
            _save_payload(
                {
                    **irp.base_payload(
                        job_id=job_id,
                        owner_uid=_owner(),
                        content_hash=str(content_hash or ""),
                        completed="debone",
                    ),
                    "pages": list(pdf_pages or []),
                    "text": text,
                    "warnings": list(warnings),
                    "sentences": [irp.sentence_to_dict(s) for s in sentences],
                    "debone_ok": debone_ok,
                    "title": title,
                    "references": references,
                }
            )
        else:
            # resumed — still normalize glyphs on EN text
            sentences = [
                Sentence(
                    id=s.id,
                    text=normalize_scientific_glyphs(s.text),
                    section=s.section,
                    start_char=s.start_char,
                    end_char=s.end_char,
                    text_ko=s.text_ko or "",
                    text_ko_stage=s.text_ko_stage or "",
                )
                for s in sentences
            ]

        # WHY: design/45 — 번역 전에 영어 세션을 먼저 열어 읽기 시작
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
            _save_payload(
                {
                    **irp.base_payload(
                        job_id=job_id,
                        owner_uid=_owner(),
                        content_hash=str(content_hash or ""),
                        completed="ready",
                    ),
                    "pages": list(pdf_pages or []),
                    "text": text,
                    "warnings": list(warnings),
                    "sentences": [irp.sentence_to_dict(s) for s in session.sentences],
                    "debone_ok": debone_ok,
                    "title": title,
                    "references": references,
                    "translate_digests": dict(session.translate_digests or {}),
                    "cache_id": str(cache_entry.get("id") or ""),
                }
            )
        _job_publish_partial(job_id, early, message="읽기 가능 · 번역 중")

        # design/99 — skip Gemini KO when client opted out (mobile Settings).
        job_meta = _JOBS.get(job_id) or {}
        want_translate = bool(job_meta.get("want_translate", True))

        if skip_translate and want_translate:
            # design/112 — payload already carried KO; do not re-bill Gemini.
            floor = ij.stage_percent_floor("translate")
            _job_set(
                job_id,
                percent=max(
                    floor, int((_JOBS.get(job_id) or {}).get("percent") or floor)
                ),
                stage="translate",
                message="번역 이어받음",
            )
            packed = _pack(pending=False)
            if cache_entry:
                packed["cache_id"] = cache_entry.get("id")
                packed["cached"] = True
                packed["has_source"] = bool(cache_entry.get("has_source"))
            _job_publish_partial(job_id, packed, message="번역 이어받음")
        elif want_translate and gemini_available():
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
                # Durable translate boundary for reclaim skip (owner payload only).
                if index > 0 and index % 8 == 0:
                    _save_payload(
                        {
                            **irp.base_payload(
                                job_id=job_id,
                                owner_uid=_owner(),
                                content_hash=str(content_hash or ""),
                                completed="translate",
                            ),
                            "pages": list(pdf_pages or []),
                            "text": text,
                            "warnings": list(warnings),
                            "sentences": [
                                irp.sentence_to_dict(s) for s in session.sentences
                            ],
                            "debone_ok": debone_ok,
                            "title": title,
                            "references": references,
                            "translate_digests": dict(
                                session.translate_digests or {}
                            ),
                            "cache_id": str(
                                (cache_entry or {}).get("id") or ""
                            ),
                        }
                    )

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
        elif want_translate:
            warnings.append("translate_skipped_no_gemini")
        else:
            warnings.append("translate_skipped_opt_out")

        if want_translate:
            _job_set(job_id, percent=98, stage="save", message="번역 저장 중")
            cache_entry = await asyncio.to_thread(
                save_paper_session,
                session,
                debone=debone_ok,
                source=kind,
                source_path=tmp_path,
                content_hash=content_hash,
            )
            if (
                cache_entry is None
                and debone_ok
                and "cache_skip_short_title" not in warnings
            ):
                warnings.append("cache_skip_short_title")

        data = _pack(pending=False)
        if cache_entry:
            data["cache_id"] = cache_entry.get("id")
            data["cached"] = True
            data["has_source"] = bool(cache_entry.get("has_source"))
        else:
            # design/108 — fail-closed: never terminal-success without durable cache_id.
            # WHY: client mapped bare message「완료」→「보관 저장 실패: 완료」(모순·고착).
            # EDGE: keep ingest upload blob (do not call _finish_job) so reclaim/retry can run.
            if "cache_skip_short_title" in warnings or not session.sentences:
                reason = (
                    "논문 제목이 너무 짧거나 문장이 없어 보관함에 넣지 못했습니다. "
                    "제목이 분명한 PDF인지 확인해 주세요."
                )
            else:
                reason = (
                    "처리는 끝났지만 보관함 저장에 실패했습니다. "
                    "잠시 후 다시 시도해 주세요."
                )
            job_err = _JOBS.get(job_id)
            if job_err is not None:
                job_err["done"] = True
                job_err["error"] = reason
                job_err["percent"] = int(job_err.get("percent") or 98)
                job_err["stage"] = "error"
                job_err["message"] = reason
                job_err["result"] = None
                _persist_job(job_id, job_err, force=True)
            return

        # design/80 — shadowing chunk plans (per-uid) when client opted in.
        want_chunks = bool(job_meta.get("want_shadowing_chunks"))
        cache_id = (cache_entry or {}).get("id") if cache_entry else None
        owner = str(job_meta.get("owner_uid") or "")
        if want_chunks and cache_id and owner:
            from sentence_reading.llm.shadowing_practice import (
                shadowing_practice_enabled,
            )
            from sentence_reading.llm import shadowing_chunks as sc

            if shadowing_practice_enabled() and gemini_available():
                _job_set(
                    job_id,
                    percent=99,
                    stage="shadowing_chunks",
                    message="쉐도잉 연습 구간 준비 중",
                )
                try:
                    set_gcs_uid(owner)
                    rows = []
                    for i, s in enumerate(session.sentences):
                        sid = getattr(s, "id", None) or str(i)
                        text = getattr(s, "text", None) or getattr(s, "text_en", None) or ""
                        rows.append({"id": str(sid), "text": str(text)})
                    plan = await asyncio.to_thread(
                        sc.build_chunk_plan,
                        uid=owner,
                        cache_id=str(cache_id),
                        sentences=rows,
                    )
                    data["shadowing_chunks"] = {
                        "status": plan.get("status"),
                        "error": plan.get("error"),
                        "sentence_count": len(plan.get("sentences") or {}),
                        "progress": plan.get("progress"),
                    }
                    # design/113 — pending is not failure; mobile open continues slices.
                    if plan.get("status") == "pending":
                        warnings.append("shadowing_chunks_pending")
                    elif plan.get("status") != "ok":
                        warnings.append(
                            "shadowing_chunks_failed:"
                            + str(plan.get("error") or "error")[:80]
                        )
                except Exception as exc:  # noqa: BLE001
                    warnings.append(f"shadowing_chunks_failed:{str(exc)[:80]}")
                    data["shadowing_chunks"] = {
                        "status": "error",
                        "error": "build_failed",
                        "sentence_count": 0,
                    }
                finally:
                    reset_gcs_uid()
            elif want_chunks and not shadowing_practice_enabled():
                data["shadowing_chunks"] = {
                    "status": "skipped",
                    "error": "shadowing_disabled",
                    "sentence_count": 0,
                }
            elif want_chunks and not gemini_available():
                data["shadowing_chunks"] = {
                    "status": "error",
                    "error": "gemini_unavailable",
                    "sentence_count": 0,
                }
                warnings.append("shadowing_chunks_failed:gemini_unavailable")

        if warnings:
            data["warnings"] = list(dict.fromkeys(list(data.get("warnings") or []) + warnings))

        _finish_job(
            job_id,
            data,
            message="완료 · 제목으로 보관됨" if cache_entry else "완료",
        )
    except Exception as exc:  # noqa: BLE001
        job = _JOBS.get(job_id)
        if job is not None:
            job["done"] = True
            # WHY: user-facing only — no stack / paths / tokens.
            job["error"] = str(exc)
            job["percent"] = job.get("percent", 0)
            job["stage"] = "error"
            # WHY: durable error so mobile reattach does not spin on stale queued.
            # EDGE: keep ingest_payload for reclaim mid-stage skip (not a success).
            _persist_job(job_id, job, force=True)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        # 오래된 job 정리 (GCS copy remains for reattach until TTL/overwrite)
        while len(_JOBS) > 12:
            oldest = next(iter(_JOBS))
            if oldest == job_id:
                break
            del _JOBS[oldest]


def _begin_ingest_from_bytes(
    raw: bytes,
    filename: str,
    kind: str,
    *,
    owner_uid: str,
    want_shadowing_chunks: bool = False,
    want_translate: bool = True,
) -> dict:
    """Shared start path for multipart + chunked-complete (design/72)."""
    from sentence_reading.llm import ingest_jobs_gcs as ij

    suffix = ".pdf" if kind == "pdf" else ".docx"
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(raw)
        tmp_path = Path(tmp.name)

    content_hash = hashlib.sha256(raw).hexdigest()
    safe_name = ij.safe_filename(filename)
    _JOBS[job_id] = {
        "percent": 1,
        "stage": "queued",
        "message": "시작해요",
        "done": False,
        "error": None,
        "result": None,
        "owner_uid": owner_uid,
        "content_hash": content_hash,
        "filename": safe_name,
        # design/80 — client opt-in only; server kill checked again at build time.
        "want_shadowing_chunks": bool(want_shadowing_chunks),
        # design/99 — default True (web); mobile sends translate=0 to skip.
        "want_translate": bool(want_translate),
    }
    # WHY (design/71): durable job + source blob so poll/reattach survives instance hop.
    if owner_uid:
        try:
            ij.save_ingest_upload(
                job_id, raw, owner_uid=owner_uid, suffix=suffix
            )
        except Exception:  # noqa: BLE001
            pass
        _persist_job(job_id, _JOBS[job_id], force=True)
    asyncio.create_task(
        _run_ingest_job(
            job_id, tmp_path, filename, kind, content_hash=content_hash
        )
    )
    return {
        "ok": True,
        "job_id": job_id,
        "percent": 1,
        "message": "업로드 완료, 읽기 시작",
        "content_hash": content_hash,
    }



@app.get("/api/shadowing/chunks/{cache_id}")
def shadowing_chunks_get(request: Request, cache_id: str) -> JSONResponse:
    """design/80 — load per-uid chunk plan (no cross-user)."""
    from sentence_reading.llm import shadowing_chunks as sc
    from sentence_reading.llm.shadowing_practice import shadowing_practice_enabled

    denied = _paid_access_denied(request)
    if denied is not None:
        return denied
    if not shadowing_practice_enabled():
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": "shadowing_disabled",
                "message": "쉐도잉 연습이 서버에서 꺼져 있습니다.",
            },
        )
    user = _request_user(request)
    if user is None:
        return JSONResponse(
            status_code=401,
            content={"ok": False, "error": "auth_required", "message": "로그인이 필요합니다."},
        )
    cid = sc.safe_cache_id(cache_id)
    if not cid:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "invalid_cache_id", "message": "논문 id가 올바르지 않습니다."},
        )
    try:
        set_gcs_uid(user.uid)
        plan = sc.load_chunk_plan(uid=user.uid, cache_id=cid)
    finally:
        reset_gcs_uid()
    return JSONResponse({"ok": True, "plan": plan})


@app.post("/api/shadowing/chunks/{cache_id}/build")
async def shadowing_chunks_build(
    request: Request, cache_id: str, payload: dict = Body(default_factory=dict)
) -> JSONResponse:
    """design/80 — backfill / retry. Requires client practice_enabled true."""
    from sentence_reading.llm import shadowing_chunks as sc
    from sentence_reading.llm.shadowing_practice import shadowing_practice_enabled

    denied = _paid_access_denied(request)
    if denied is not None:
        return denied
    if not shadowing_practice_enabled():
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": "shadowing_disabled",
                "message": "쉐도잉 연습이 서버에서 꺼져 있습니다.",
            },
        )
    user = _request_user(request)
    if user is None:
        return JSONResponse(
            status_code=401,
            content={"ok": False, "error": "auth_required", "message": "로그인이 필요합니다."},
        )
    # WHY: mirror translate-on gate — client setting must be on; no silent build.
    if not isinstance(payload, dict) or not payload.get("practice_enabled"):
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": "practice_off",
                "message": "설정에서 쉐도잉 연습을 켠 뒤 다시 시도해 주세요.",
            },
        )
    cid = sc.safe_cache_id(cache_id)
    if not cid:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "invalid_cache_id", "message": "논문 id가 올바르지 않습니다."},
        )
    if not gemini_available():
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": "gemini_unavailable",
                "message": "연습 구간을 만들 수 없습니다. 잠시 후 다시 시도해 주세요.",
            },
        )
    rows = payload.get("sentences") if isinstance(payload.get("sentences"), list) else None
    if not rows:
        # Load from cached paper session for this user.
        from sentence_reading.cache.paper_cache import load_cached_session

        try:
            set_gcs_uid(user.uid)
            loaded = load_cached_session(cid)
        finally:
            reset_gcs_uid()
        if loaded is None:
            return JSONResponse(
                status_code=404,
                content={
                    "ok": False,
                    "error": "paper_not_found",
                    "message": "보관된 논문을 찾을 수 없습니다.",
                },
            )
        session, _info = loaded
        rows = []
        for i, s in enumerate(session.sentences):
            sid = getattr(s, "id", None) or str(i)
            text = getattr(s, "text", None) or ""
            rows.append({"id": str(sid), "text": str(text)})
    try:
        set_gcs_uid(user.uid)
        plan = await asyncio.to_thread(
            sc.build_chunk_plan, uid=user.uid, cache_id=cid, sentences=rows
        )
    except PermissionError:
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": "shadowing_disabled",
                "message": "쉐도잉 연습이 서버에서 꺼져 있습니다.",
            },
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": str(exc)[:80],
                "message": "연습 구간 요청이 올바르지 않습니다.",
            },
        )
    finally:
        reset_gcs_uid()
    status = str(plan.get("status") or "")
    # design/113 — pending is an honest in-progress slice (HTTP 200), not gateway 504.
    if status == "pending":
        return JSONResponse(
            {
                "ok": True,
                "continue": True,
                "plan": plan,
                "error": None,
                "message": "연습 구간을 이어서 준비하는 중…",
            }
        )
    ok = status == "ok"
    return JSONResponse(
        {
            "ok": ok,
            "continue": False,
            "plan": plan,
            "error": None if ok else (plan.get("error") or "build_failed"),
            "message": None
            if ok
            else "연습 구간을 만들지 못했습니다. 다시 시도해 주세요.",
        },
        status_code=200 if ok else 502,
    )




@app.get("/api/shadowing/takes/{cache_id}")
def shadowing_takes_get(request: Request, cache_id: str) -> JSONResponse:
    """design/82 — load per-uid practice takes (no cross-user)."""
    from sentence_reading.llm import shadowing_takes as st
    from sentence_reading.llm.shadowing_practice import shadowing_practice_enabled

    denied = _paid_access_denied(request)
    if denied is not None:
        return denied
    if not shadowing_practice_enabled():
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": "shadowing_disabled",
                "message": "쉐도잉 연습이 서버에서 꺼져 있습니다.",
            },
        )
    user = _request_user(request)
    if user is None:
        return JSONResponse(
            status_code=401,
            content={"ok": False, "error": "auth_required", "message": "로그인이 필요합니다."},
        )
    from sentence_reading.llm.shadowing_chunks import safe_cache_id as _safe_cid

    cid = _safe_cid(cache_id)
    if not cid:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "invalid_cache_id", "message": "논문 id가 올바르지 않습니다."},
        )
    try:
        set_gcs_uid(user.uid)
        takes = st.load_takes(uid=user.uid, cache_id=cid)
    finally:
        reset_gcs_uid()
    return JSONResponse({"ok": True, "takes": takes})


@app.post("/api/shadowing/takes/{cache_id}")
async def shadowing_takes_post(
    request: Request, cache_id: str, payload: dict = Body(default_factory=dict)
) -> JSONResponse:
    """design/82 — save one chunk take (recorded|skipped) or cursor. Session uid only."""
    from sentence_reading.llm import shadowing_takes as st
    from sentence_reading.llm.shadowing_chunks import safe_cache_id as _safe_cid
    from sentence_reading.llm.shadowing_practice import shadowing_practice_enabled

    denied = _paid_access_denied(request)
    if denied is not None:
        return denied
    if not shadowing_practice_enabled():
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": "shadowing_disabled",
                "message": "쉐도잉 연습이 서버에서 꺼져 있습니다.",
            },
        )
    user = _request_user(request)
    if user is None:
        return JSONResponse(
            status_code=401,
            content={"ok": False, "error": "auth_required", "message": "로그인이 필요합니다."},
        )
    # WHY: mirror translate-on — client must affirm practice_enabled (no silent write).
    if not isinstance(payload, dict) or not payload.get("practice_enabled"):
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": "practice_off",
                "message": "설정에서 쉐도잉 연습을 켠 뒤 다시 시도해 주세요.",
            },
        )
    # EDGE: ignore client user_id if present (authz).
    cid = _safe_cid(cache_id)
    if not cid:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "invalid_cache_id", "message": "논문 id가 올바르지 않습니다."},
        )
    action = str(payload.get("action") or "take").strip().lower()
    try:
        set_gcs_uid(user.uid)
        takes = st.load_takes(uid=user.uid, cache_id=cid)
        if action == "cursor":
            takes = st.set_cursor(
                takes,
                sentence_id=payload.get("sentence_id"),
                chunk_index=int(payload.get("chunk_index") or 0),
            )
        else:
            takes = st.apply_take(
                takes,
                sentence_id=str(payload.get("sentence_id") or ""),
                chunk_index=int(payload.get("chunk_index") or 0),
                chunk_count=int(payload.get("chunk_count") or 1),
                status=str(payload.get("status") or ""),
                blob_key=payload.get("blob_key"),
                mime=payload.get("mime"),
            )
        st.save_takes(uid=user.uid, cache_id=cid, takes=takes)
    except PermissionError:
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": "shadowing_disabled",
                "message": "쉐도잉 연습이 서버에서 꺼져 있습니다.",
            },
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": str(exc)[:80],
                "message": "연습 기록 요청이 올바르지 않습니다.",
            },
        )
    finally:
        reset_gcs_uid()
    return JSONResponse({"ok": True, "takes": takes})


@app.post("/api/shadowing/takes/{cache_id}/continue")
async def shadowing_takes_continue(
    request: Request, cache_id: str, payload: dict = Body(default_factory=dict)
) -> JSONResponse:
    """design/82 — list full-pass sentence takes only (section continue-listen)."""
    from sentence_reading.llm import shadowing_takes as st
    from sentence_reading.llm.shadowing_chunks import safe_cache_id as _safe_cid
    from sentence_reading.llm.shadowing_practice import shadowing_practice_enabled

    denied = _paid_access_denied(request)
    if denied is not None:
        return denied
    if not shadowing_practice_enabled():
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": "shadowing_disabled",
                "message": "쉐도잉 연습이 서버에서 꺼져 있습니다.",
            },
        )
    user = _request_user(request)
    if user is None:
        return JSONResponse(
            status_code=401,
            content={"ok": False, "error": "auth_required", "message": "로그인이 필요합니다."},
        )
    if not isinstance(payload, dict) or not payload.get("practice_enabled"):
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": "practice_off",
                "message": "설정에서 쉐도잉 연습을 켠 뒤 다시 시도해 주세요.",
            },
        )
    cid = _safe_cid(cache_id)
    if not cid:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "invalid_cache_id", "message": "논문 id가 올바르지 않습니다."},
        )
    ids = payload.get("sentence_ids") if isinstance(payload.get("sentence_ids"), list) else []
    ids = [str(x) for x in ids][:400]
    try:
        set_gcs_uid(user.uid)
        takes = st.load_takes(uid=user.uid, cache_id=cid)
        playlist = st.full_pass_blob_keys(takes, ids)
    finally:
        reset_gcs_uid()
    return JSONResponse({"ok": True, "playlist": playlist})


@app.post("/api/ingest/uploads")
async def ingest_upload_create(
    request: Request, payload: dict = Body(default_factory=dict)
) -> JSONResponse:
    """design/72 — start chunked upload session (all PDFs)."""
    from sentence_reading.llm import ingest_chunked as ic

    denied = _paid_access_denied(request)
    if denied is not None:
        return denied
    if not ic.chunked_upload_enabled():
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": "chunked_upload_disabled",
                "message": "조각 업로드가 일시적으로 꺼져 있습니다.",
            },
        )
    user = _request_user(request)
    if user is None:
        return JSONResponse(
            status_code=401,
            content={
                "ok": False,
                "error": "auth_required",
                "message": "로그인이 필요합니다.",
            },
        )
    # WHY after auth: count only real session uids (not anon probes).
    limited = _ingest_rate_limited(request, "upload_create")
    if limited is not None:
        return limited
    body = payload if isinstance(payload, dict) else {}
    filename = str(body.get("filename") or "document.pdf")
    kind = _source_kind(filename)
    if kind != "pdf":
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": "unsupported_type",
                "message": "조각 업로드는 PDF만 지원합니다.",
            },
        )
    try:
        size = int(body.get("size") or 0)
    except (TypeError, ValueError):
        size = 0
    content_hash = str(body.get("content_hash") or "").strip().lower()
    view = ic.create_upload_session(
        owner_uid=user.uid,
        content_hash=content_hash,
        filename=filename,
        size=size,
    )
    if view is None:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": "bad_upload_session",
                "message": "업로드 세션을 만들 수 없습니다. 파일 크기·해시를 확인해 주세요.",
            },
        )
    return JSONResponse(view)


@app.get("/api/ingest/uploads/{upload_id}")
def ingest_upload_status(request: Request, upload_id: str) -> JSONResponse:
    """Resume probe — returns offset + prefix_sha256 for integrity check."""
    from sentence_reading.llm import ingest_chunked as ic

    user = _request_user(request)
    if user is None:
        return JSONResponse(
            status_code=401,
            content={
                "ok": False,
                "error": "auth_required",
                "message": "로그인이 필요합니다.",
            },
        )
    view = ic.get_upload(upload_id, owner_uid=user.uid)
    if view is None:
        return JSONResponse(
            status_code=404,
            content={
                "ok": False,
                "error": "upload_not_found",
                "message": "업로드 세션을 찾을 수 없습니다.",
            },
        )
    return JSONResponse(view)


@app.put("/api/ingest/uploads/{upload_id}")
async def ingest_upload_put(request: Request, upload_id: str) -> JSONResponse:
    """Append one contiguous chunk (raw body). Query: offset. Header: X-Chunk-Sha256."""
    from sentence_reading.llm import ingest_chunked as ic

    denied = _paid_access_denied(request)
    if denied is not None:
        return denied
    user = _request_user(request)
    if user is None:
        return JSONResponse(
            status_code=401,
            content={
                "ok": False,
                "error": "auth_required",
                "message": "로그인이 필요합니다.",
            },
        )
    limited = _ingest_rate_limited(request, "upload_put")
    if limited is not None:
        return limited
    if not ic.valid_upload_id(upload_id):
        return JSONResponse(
            status_code=404,
            content={
                "ok": False,
                "error": "upload_not_found",
                "message": "업로드 세션을 찾을 수 없습니다.",
            },
        )
    try:
        offset = int(request.query_params.get("offset") or -1)
    except (TypeError, ValueError):
        offset = -1
    if offset < 0:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": "bad_offset",
                "message": "offset 이 필요합니다.",
            },
        )
    data = await request.body()
    chunk_sha = (request.headers.get("X-Chunk-Sha256") or "").strip()
    try:
        view = ic.append_chunk(
            upload_id,
            owner_uid=user.uid,
            offset=offset,
            data=data,
            chunk_sha256=chunk_sha or None,
        )
    except LookupError:
        return JSONResponse(
            status_code=404,
            content={
                "ok": False,
                "error": "upload_not_found",
                "message": "업로드 세션을 찾을 수 없습니다.",
            },
        )
    except ValueError as exc:
        code = str(exc)
        return JSONResponse(
            status_code=409 if code == "offset_mismatch" else 400,
            content={
                "ok": False,
                "error": code,
                "message": "조각 업로드를 이어갈 수 없습니다. 무결성 검사 후 다시 시도해 주세요.",
            },
        )
    except Exception:  # noqa: BLE001
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "chunk_store_failed",
                "message": "조각 저장에 실패했습니다.",
            },
        )
    return JSONResponse(view)


@app.post("/api/ingest/uploads/{upload_id}/complete")
async def ingest_upload_complete(
    request: Request, upload_id: str
) -> JSONResponse:
    """Assemble chunks → verify content_hash → start ingest job."""
    from sentence_reading.llm import ingest_chunked as ic

    denied = _paid_access_denied(request)
    if denied is not None:
        return denied
    user = _request_user(request)
    if user is None:
        return JSONResponse(
            status_code=401,
            content={
                "ok": False,
                "error": "auth_required",
                "message": "로그인이 필요합니다.",
            },
        )
    try:
        raw, meta = ic.assemble_and_verify(upload_id, owner_uid=user.uid)
    except LookupError:
        return JSONResponse(
            status_code=404,
            content={
                "ok": False,
                "error": "upload_not_found",
                "message": "업로드 세션을 찾을 수 없습니다.",
            },
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": str(exc),
                "message": "업로드 조각을 검증하지 못했습니다. 처음부터 다시 올려 주세요.",
            },
        )
    except Exception:  # noqa: BLE001
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "assemble_failed",
                "message": "업로드 조립에 실패했습니다.",
            },
        )
    filename = str(meta.get("filename") or "document.pdf")
    limited = _ingest_rate_limited(request, "ingest_start")
    if limited is not None:
        return limited
    out = _begin_ingest_from_bytes(
        raw,
        filename,
        "pdf",
        owner_uid=user.uid,
        want_shadowing_chunks=_want_shadowing_chunks(request),
        want_translate=_want_translate(request),
    )
    try:
        ic.delete_upload_session(upload_id, owner_uid=user.uid)
    except Exception:  # noqa: BLE001
        pass
    return JSONResponse(out)


@app.post("/api/ingest")
async def ingest(request: Request, file: UploadFile = File(...)) -> JSONResponse:
    """PDF/DOCX 업로드 → 백그라운드 정제. job_id 로 진행률 폴링 (웹·호환)."""
    denied = _paid_access_denied(request)
    if denied is not None:
        return denied
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

    user = _request_user(request)
    owner_uid = user.uid if user is not None else ""
    limited = _ingest_rate_limited(request, "ingest_start")
    if limited is not None:
        return limited
    return JSONResponse(
        _begin_ingest_from_bytes(
            raw,
            filename,
            kind,
            owner_uid=owner_uid,
            want_shadowing_chunks=_want_shadowing_chunks(request),
            want_translate=_want_translate(request),
        )
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
