"""Waveform to pronunciation symbols. Loaded only when a practice take arrives.

Every step reports why it stopped. A silent empty answer used to look the same
whether ffmpeg was missing, the container could not seek the recording, or the
model never loaded.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import threading
import time

_LOCK = threading.Lock()
_READY = False
_PROCESSOR = None
_MODEL = None
_NAME = "facebook/wav2vec2-lv-60-espeak-cv-ft"
_LOAD_FAIL = ""


def hear_phones(data: bytes) -> str:
    """Space-separated phones from the recording. Empty when the model cannot run."""
    phones, _report = hear_phones_report(data)
    return phones


def hear_phones_report(data: bytes) -> tuple[str, dict[str, object]]:
    """Phones plus a short code for the step that stopped, for the evidence row."""
    report: dict[str, object] = {
        "hear_code": "ok",
        "hear_bytes": len(data or b""),
        "ffmpeg": 1 if shutil.which("ffmpeg") else 0,
        "pcm_n": 0,
        "decode_ms": 0,
        "load_ms": 0,
        "infer_ms": 0,
        "phone_n": 0,
        "hear_detail": "none",
    }
    if not data:
        report["hear_code"] = "no_audio"
        return "", report
    if not report["ffmpeg"]:
        report["hear_code"] = "ffmpeg_missing"
        return "", report

    clock = time.monotonic()
    try:
        pcm = _pcm16k(data)
    except _DecodeError as exc:
        report["hear_code"] = "decode_failed"
        report["hear_detail"] = _snake(str(exc))
        report["decode_ms"] = int((time.monotonic() - clock) * 1000)
        return "", report
    except (OSError, subprocess.TimeoutExpired) as exc:
        report["hear_code"] = "decode_crashed"
        report["hear_detail"] = _snake(type(exc).__name__)
        report["decode_ms"] = int((time.monotonic() - clock) * 1000)
        return "", report
    report["decode_ms"] = int((time.monotonic() - clock) * 1000)
    if pcm is None:
        report["hear_code"] = "decode_empty"
        return "", report
    report["pcm_n"] = int(pcm.shape[0])
    if int(pcm.shape[0]) < 1600:
        report["hear_code"] = "too_short"
        return "", report

    clock = time.monotonic()
    try:
        _load()
    except Exception as exc:  # noqa: BLE001
        report["hear_code"] = "load_failed"
        report["hear_detail"] = _snake(type(exc).__name__)
        report["load_ms"] = int((time.monotonic() - clock) * 1000)
        return "", report
    report["load_ms"] = int((time.monotonic() - clock) * 1000)
    if _PROCESSOR is None or _MODEL is None:
        report["hear_code"] = "model_missing"
        report["hear_detail"] = _snake(_LOAD_FAIL or "none")
        return "", report

    import torch

    clock = time.monotonic()
    try:
        with _LOCK:
            values = _PROCESSOR(
                pcm, sampling_rate=16000, return_tensors="pt"
            ).input_values
            with torch.no_grad():
                logits = _MODEL(values).logits
            ids = torch.argmax(logits, dim=-1)
            text = _PROCESSOR.batch_decode(ids)[0]
    except Exception as exc:  # noqa: BLE001
        report["hear_code"] = "infer_failed"
        report["hear_detail"] = _snake(type(exc).__name__)
        report["infer_ms"] = int((time.monotonic() - clock) * 1000)
        return "", report
    report["infer_ms"] = int((time.monotonic() - clock) * 1000)
    out = " ".join(str(text).split())
    report["phone_n"] = len(out.split())
    if not out:
        report["hear_code"] = "empty_text"
    return out, report


class _DecodeError(Exception):
    """ffmpeg refused the recording; the message carries its first line."""


def _snake(raw: object) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(raw or "").strip().lower()).strip("_")
    return (text[:63] or "none")


def _load() -> None:
    global _READY, _PROCESSOR, _MODEL, _LOAD_FAIL
    if _READY:
        return
    with _LOCK:
        if _READY:
            return
        try:
            from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

            _PROCESSOR = Wav2Vec2Processor.from_pretrained(_NAME)
            _MODEL = Wav2Vec2ForCTC.from_pretrained(_NAME)
            _MODEL.eval()
        except Exception as exc:  # noqa: BLE001
            _LOAD_FAIL = type(exc).__name__
            _PROCESSOR = None
            _MODEL = None
            raise
        _LOAD_FAIL = ""
        _READY = True


def _pcm16k(data: bytes):
    import torch

    # The phone sends MP4/M4A. Its index sits at the end of the file, so ffmpeg
    # has to seek and a pipe cannot be seeked. The bytes go to a file first.
    handle, path = tempfile.mkstemp(suffix=".m4a")
    try:
        with os.fdopen(handle, "wb") as fh:
            fh.write(data)
        done = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                path,
                "-ac",
                "1",
                "-ar",
                "16000",
                "-f",
                "f32le",
                "pipe:1",
            ],
            capture_output=True,
            timeout=20,
            check=False,
        )
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    if done.returncode != 0 or not done.stdout:
        why = (done.stderr or b"").decode("utf-8", "replace").strip()
        first = why.splitlines()[-1] if why else "no_output"
        raise _DecodeError(first[:80])
    raw = done.stdout
    if len(raw) % 4:
        raw = raw[: len(raw) - (len(raw) % 4)]
    clone = bytearray(raw)
    return torch.frombuffer(clone, dtype=torch.float32)


def warm_model() -> bool:
    """True when the model is in memory. Safe to call more than once."""
    try:
        _load()
    except Exception:  # noqa: BLE001
        return False
    return _MODEL is not None


def warm_report() -> dict[str, object]:
    """Whether the model is in memory, and the failure name when it is not."""
    clock = time.monotonic()
    ok = warm_model()
    return {
        "warm_ok": 1 if ok else 0,
        "warm_ms": int((time.monotonic() - clock) * 1000),
        "warm_detail": _snake(_LOAD_FAIL or "none"),
        "ffmpeg": 1 if shutil.which("ffmpeg") else 0,
    }
