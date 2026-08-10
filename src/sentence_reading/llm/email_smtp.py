# -*- coding: utf-8 -*-
"""Minimal SMTP mailer for magic-link (design/77).

Fail-closed: if host/from missing, send raises — API must not claim success.
Never log recipients beyond debug hash; never log message bodies with tokens.
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

from sentence_reading.llm.env import load_asr_env

log = logging.getLogger(__name__)


def smtp_configured() -> bool:
    load_asr_env()
    host = (os.environ.get("ASR_SMTP_HOST") or "").strip()
    from_addr = (os.environ.get("ASR_SMTP_FROM") or "").strip()
    return bool(host and from_addr)


def smtp_config_error() -> str | None:
    """Human-safe reason when SMTP cannot send (no secrets)."""
    if smtp_configured():
        return None
    return "smtp_not_configured"


def send_magic_link_email(*, to_email: str, open_url: str) -> None:
    """
    Send login link. Raises ValueError('smtp_not_configured') or RuntimeError on SMTP failure.
    INVARIANT: do not include session cookies; only the one-time open URL.
    """
    load_asr_env()
    host = (os.environ.get("ASR_SMTP_HOST") or "").strip()
    from_addr = (os.environ.get("ASR_SMTP_FROM") or "").strip()
    if not host or not from_addr:
        raise ValueError("smtp_not_configured")
    to_addr = (to_email or "").strip()
    if not to_addr or "@" not in to_addr or len(to_addr) > 320:
        raise ValueError("bad_email")
    url = (open_url or "").strip()
    if not url.startswith("https://") and not url.startswith("http://"):
        raise ValueError("bad_url")
    if len(url) > 2000:
        raise ValueError("bad_url")

    port_raw = (os.environ.get("ASR_SMTP_PORT") or "587").strip()
    try:
        port = int(port_raw)
    except ValueError:
        port = 587
    user = (os.environ.get("ASR_SMTP_USER") or "").strip()
    password = (os.environ.get("ASR_SMTP_PASS") or "").strip()
    use_ssl = (os.environ.get("ASR_SMTP_SSL") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )

    msg = EmailMessage()
    msg["Subject"] = "문장 읽기 로그인 링크"
    msg["From"] = from_addr
    msg["To"] = to_addr
    # WHY: plain text only — no HTML injection surface for mail clients.
    msg.set_content(
        "문장 읽기 로그인 링크입니다.\n\n"
        "아래 주소를 열면 앱으로 이동합니다. 링크는 짧은 시간·1회만 유효합니다.\n\n"
        f"{url}\n\n"
        "요청하지 않았다면 이 메일을 무시하세요.\n"
    )

    try:
        if use_ssl or port == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as smtp:
                if user:
                    smtp.login(user, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as smtp:
                smtp.ehlo()
                try:
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.ehlo()
                except smtplib.SMTPException:
                    # EDGE: some relays have no STARTTLS — still try auth/send.
                    pass
                if user:
                    smtp.login(user, password)
                smtp.send_message(msg)
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001
        # WHY: do not echo SMTP diagnostics (may include recipient).
        log.warning("smtp send failed: %s", type(exc).__name__)
        raise RuntimeError("smtp_send_failed") from exc
