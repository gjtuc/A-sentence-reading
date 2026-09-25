"""Waveform to pronunciation symbols. Loaded only when a practice take arrives."""

from __future__ import annotations

import subprocess
import threading

_LOCK = threading.Lock()
_READY = False
_PROCESSOR = None
_MODEL = None
_NAME = "facebook/wav2vec2-lv-60-espeak-cv-ft"


def hear_phones(data: bytes) -> str:
    """Space-separated phones from the recording. Empty when the model cannot run."""
    if not data:
        return ""
    try:
        pcm = _pcm16k(data)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return ""
    if pcm is None or int(pcm.shape[0]) < 1600:
        return ""
    try:
        _load()
    except Exception:
        return ""
    if _PROCESSOR is None or _MODEL is None:
        return ""
    import torch

    with _LOCK:
        values = _PROCESSOR(pcm, sampling_rate=16000, return_tensors="pt").input_values
        with torch.no_grad():
            logits = _MODEL(values).logits
        ids = torch.argmax(logits, dim=-1)
        text = _PROCESSOR.batch_decode(ids)[0]
    return " ".join(str(text).split())


def _load() -> None:
    global _READY, _PROCESSOR, _MODEL
    if _READY:
        return
    with _LOCK:
        if _READY:
            return
        from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

        _PROCESSOR = Wav2Vec2Processor.from_pretrained(_NAME)
        _MODEL = Wav2Vec2ForCTC.from_pretrained(_NAME)
        _MODEL.eval()
        _READY = True


def _pcm16k(data: bytes):
    import torch

    done = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "f32le",
            "pipe:1",
        ],
        input=data,
        capture_output=True,
        timeout=20,
        check=False,
    )
    if done.returncode != 0 or not done.stdout:
        raise ValueError("audio_decode_failed")
    raw = done.stdout
    if len(raw) % 4:
        raw = raw[: len(raw) - (len(raw) % 4)]
    clone = bytearray(raw)
    return torch.frombuffer(clone, dtype=torch.float32)

def warm_model() -> bool:
    """True when the model is in memory. Safe to call more than once."""
    try:
        _load()
    except Exception:
        return False
    return _MODEL is not None
