"""The sounds a native voice makes for each word of a sentence.

design/368 cut the reference loose from eSpeak, which read a dictionary rather
than listening to a voice, and left `spans[].phone` empty. Nothing has scored
since. This is what fills it.

The sentence is synthesized twice by the same voice:

* once read straight through, which is the reading a learner is asked to match
* once with a 100 ms break after every token and an SSML mark around each one,
  which is the same words with the boundaries reported

The break reading is only a stencil. Its own sounds are over-articulated, so
they are not the reference; they say how many sounds a token owns and roughly
which. The reference symbols are then picked out of the straight reading, in
order, by `hand_out`. That keeps the natural reading's sounds and the break
reading's boundaries.

A boundary is never decided by listening. Only Google's marks may say where a
word starts or ends. Frame times are allowed to sort a sound into a window a
mark already drew, and nothing else. Energy gates and posterior edges were both
tried and both moved boundaries into the wrong word.

References are content-addressed on the spoken text and the voice, cached on
local disk and best-effort in GCS, because building one costs two synthesis
calls and two model passes.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import wave
from pathlib import Path
from xml.sax.saxutils import escape

from sentence_reading.cache.paper_cache import project_root
from sentence_reading.llm.env import load_asr_env
from sentence_reading.llm.tts_speak_policy import speak_norm_version

# The break the stencil reading puts after every token, and the slack allowed
# around a mark when a sound is sorted into its window.
BREAK_MS = 100
PAD_MS = 25

# Every run of non-space characters, so a number or a unit gets its own window.
# Matching letters alone left the sounds of `2.3` and `(111)` with no owner, and
# `hand_out` then forced them onto a neighbour: one sentence handed `The`
# seventy sounds while four words got none.
_TOKEN = re.compile(r"\S+")
_SAFE_KEY = re.compile(r"^[A-Za-z0-9._-]+$")


def reference_voice() -> str:
    """The one voice every reference is built from.

    A reference has to be comparable across takes, so it cannot follow the
    random playback voice. It is part of the cache key all the same, so changing
    this rebuilds rather than serving a stale reference.
    """
    load_asr_env()
    return (os.environ.get("ASR_REF_VOICE") or "en-US-Neural2-D").strip()


def cache_key(spoken: str, voice: str) -> str:
    raw = f"{speak_norm_version()}|{voice}|{BREAK_MS}|{PAD_MS}|{spoken}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def cache_dir() -> Path:
    load_asr_env()
    raw = (os.environ.get("ASR_SOUND_REF_DIR") or "").strip()
    return Path(raw) if raw else project_root() / "data" / "sound_ref"


def ssml_marked(spoken: str) -> tuple[str, list[tuple[int, int, str]]]:
    """SSML that reads every token alone, and where each token sat in the text.

    A mark's timestamp is where the audio after it begins, so a mark only ever
    reports a start. The closing mark is what makes an end reportable, and the
    break is what keeps the closing mark from collapsing into the next opening
    one across whitespace.
    """
    spots = [(m.start(), m.end(), m.group(0)) for m in _TOKEN.finditer(spoken)]
    parts = ["<speak>"]
    for i, (_lo, _hi, token) in enumerate(spots):
        parts.append(
            f'<mark name="w{i}"/>{escape(token)}<mark name="e{i}"/>'
            f'<break time="{BREAK_MS}ms"/> '
        )
    parts.append("</speak>")
    return "".join(parts), spots


def synth_marked(ssml: str, voice: str) -> tuple[bytes, dict[str, float]]:
    """LINEAR16 at 16 kHz plus {mark name: seconds}.

    LINEAR16 so the audio decodes with the standard library and the reference
    build needs no ffmpeg. Timepoints are v1beta1 only.
    """
    from google.cloud import texttospeech_v1beta1 as tts

    load_asr_env()
    client = tts.TextToSpeechClient()
    request = tts.SynthesizeSpeechRequest(
        input=tts.SynthesisInput(ssml=ssml),
        voice=tts.VoiceSelectionParams(
            language_code="-".join(voice.split("-")[:2]), name=voice
        ),
        audio_config=tts.AudioConfig(
            audio_encoding=tts.AudioEncoding.LINEAR16, sample_rate_hertz=16000
        ),
        enable_time_pointing=[
            tts.SynthesizeSpeechRequest.TimepointType.SSML_MARK
        ],
    )
    answer = client.synthesize_speech(request=request)
    times = {p.mark_name: float(p.time_seconds) for p in answer.timepoints}
    return answer.audio_content, times


def pcm_of(raw: bytes):
    """Mono float32 at 16 kHz out of LINEAR16 wav bytes."""
    import numpy as np

    with wave.open(io.BytesIO(raw), "rb") as fh:
        if fh.getsampwidth() != 2 or fh.getnchannels() != 1:
            raise ValueError("unexpected_wav_shape")
        rate = fh.getframerate()
        frames = fh.readframes(fh.getnframes())
    pcm = np.frombuffer(frames, dtype="<i2").astype("float32") / 32768.0
    return pcm, rate


def cut_marks(
    frames: list[dict[str, object]],
    spots: list[tuple[int, int, str]],
    times: dict[str, float],
    total_s: float,
) -> list[list[str]]:
    """The sounds inside each token's own mark window.

    A token whose mark never came back gets nothing rather than a guess.
    """
    from sentence_reading.llm.hear_waveform import FRAME_MS

    pad = PAD_MS / 1000.0
    out: list[list[str]] = []
    for i, _spot in enumerate(spots):
        start = times.get(f"w{i}")
        if start is None:
            out.append([])
            continue
        stop = times.get(f"e{i}")
        if stop is None:
            # A closing mark can collapse into the next opening one. Fall back
            # to where the next token starts, not to the end of the line.
            stop = min(
                (
                    times[f"w{j}"]
                    for j in range(i + 1, len(spots))
                    if f"w{j}" in times
                ),
                default=total_s,
            )
        lo, hi = start - pad, stop + pad
        here = []
        for one in frames:
            mid = (int(one["f0"]) + int(one["f1"])) / 2 * FRAME_MS / 1000.0
            if lo <= mid < hi:
                here.append(str(one["sym"]))
        out.append(here)
    return out


def hand_out(stencil: list[list[str]], natural: list[str]) -> list[list[str]]:
    """Give the straight reading's sounds to the tokens, in order.

    Each token takes a run of the natural reading, the runs stay in order and do
    not overlap, and a sound may go to nobody. The score is how close a run is
    to that token's stencil, so a token ends up with the sounds it should own
    even though the widths differ between the two readings.

    Letting a sound go unclaimed is what keeps a punctuation-only token or a
    breath from bloating its neighbour.
    """
    from sentence_reading.llm.phone_match import overlap_ratio

    n, wide = len(stencil), len(natural)
    neg = float("-inf")
    best = [[neg] * (wide + 1) for _ in range(n + 1)]
    back: list[list[tuple[str, int] | None]] = [
        [None] * (wide + 1) for _ in range(n + 1)
    ]
    for j in range(wide + 1):
        best[0][j] = 0.0
        back[0][j] = ("skip", j - 1) if j else None
    for i in range(1, n + 1):
        want = stencil[i - 1]
        widest = len(want) + 2 if want else 0
        for j in range(wide + 1):
            if j and best[i][j - 1] > best[i][j]:
                best[i][j] = best[i][j - 1]
                back[i][j] = ("skip", j - 1)
            for width in range(0, min(widest, j) + 1):
                k = j - width
                if best[i - 1][k] == neg:
                    continue
                got = best[i - 1][k]
                if width:
                    got += overlap_ratio(want, natural[k:j])
                if got > best[i][j]:
                    best[i][j] = got
                    back[i][j] = ("take", k)
    out: list[list[str]] = [[] for _ in range(n)]
    i, j = n, wide
    while i > 0:
        move = back[i][j]
        if move is None:
            break
        kind, k = move
        if kind == "skip":
            j = k
        else:
            out[i - 1] = natural[k:j]
            i, j = i - 1, k
    return out


def build(spoken: str, *, voice: str | None = None) -> dict[str, object]:
    """Two synthesis calls and two model passes. Call `reference_for` instead."""
    from sentence_reading.llm.hear_waveform import phone_frames

    name = voice or reference_voice()
    straight, _t = synth_marked(f"<speak>{escape(spoken)}</speak>", name)
    pcm, _rate = pcm_of(straight)
    natural = [str(one["sym"]) for one in phone_frames(pcm)]

    ssml, spots = ssml_marked(spoken)
    marked, times = synth_marked(ssml, name)
    pcm2, rate2 = pcm_of(marked)
    stencil = cut_marks(
        phone_frames(pcm2), spots, times, len(pcm2) / float(rate2)
    )
    given = hand_out(stencil, natural)
    return {
        "voice": name,
        "words": [
            {"lo": lo, "hi": hi, "sounds": " ".join(given[i])}
            for i, (lo, hi, _tok) in enumerate(spots)
        ],
        "natural_n": len(natural),
        "mark_n": len(times),
    }


def _read_cache(key: str) -> dict[str, object] | None:
    path = cache_dir() / f"{key}.json"
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    try:
        from sentence_reading.llm.gcs_sync import download_bytes, object_name

        obj = object_name("sound_ref", f"{key}.json")
        if not obj:
            return None
        data = download_bytes(obj)
        if not data:
            return None
        got = json.loads(data.decode("utf-8"))
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(got, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            pass
        return got
    except Exception:  # noqa: BLE001
        return None


def _write_cache(key: str, got: dict[str, object]) -> None:
    body = json.dumps(got, ensure_ascii=False)
    try:
        path = cache_dir() / f"{key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    except OSError:
        pass
    try:
        from sentence_reading.llm.gcs_sync import object_name, upload_bytes

        obj = object_name("sound_ref", f"{key}.json")
        if obj:
            upload_bytes(obj, body.encode("utf-8"), content_type="application/json")
    except Exception:  # noqa: BLE001
        pass


def reference_for(
    spoken: str, *, voice: str | None = None, allow_build: bool = True
) -> dict[str, object] | None:
    """Per-token reference sounds for a spoken line, cache first.

    Returns None when there is nothing to build from, or when the reference is
    absent and `allow_build` is false. A caller on a request path should pass
    `allow_build=False` and let a warm step do the synthesis.
    """
    text = (spoken or "").strip()
    if not text:
        return None
    name = voice or reference_voice()
    key = cache_key(text, name)
    if not _SAFE_KEY.match(key):
        return None
    got = _read_cache(key)
    if got is not None:
        return got
    if not allow_build:
        return None
    got = build(text, voice=name)
    _write_cache(key, got)
    return got


def attach_sounds(
    spans: list[dict[str, int]], got: dict[str, object] | None
) -> int:
    """Put a `phone` on every span, from the reference tokens it was read as.

    Each span carries the slice of the spoken text its printed word consumed, so
    a printed `nm` read as `nanometers` claims that one token and a chunk read as
    two words claims both.

    A reference token is given away once. Printed `2.3` is two spans, `2` and
    `3`, because the display splits on the dot, while the voice reads it as one
    token `2.3`. Handing that token's sounds to both would score the same audio
    twice and let one slip pass on the other's sounds. The first span takes it
    and the rest are left empty, which puts them under design/366's three-sound
    floor so they are not judged at all.

    Returns how many spans came out with a reference.
    """
    words = list((got or {}).get("words") or [])
    taken = [False] * len(words)
    filled = 0
    for span in spans:
        lo = span.get("spoken_lo")
        hi = span.get("spoken_hi")
        pieces: list[str] = []
        if isinstance(lo, int) and isinstance(hi, int) and hi > lo:
            for i, one in enumerate(words):
                if taken[i]:
                    continue
                try:
                    a, b = int(one["lo"]), int(one["hi"])
                except (KeyError, TypeError, ValueError):
                    continue
                if a < hi and lo < b:
                    piece = str(one.get("sounds") or "").strip()
                    taken[i] = True
                    if piece:
                        pieces.append(piece)
        span["phone"] = " ".join(pieces)
        if pieces:
            filled += 1
    return filled


def strip_ranges(spans: list[dict[str, int]]) -> None:
    """Drop the walk's bookkeeping before the spans go on the wire."""
    for span in spans:
        span.pop("spoken_lo", None)
        span.pop("spoken_hi", None)
