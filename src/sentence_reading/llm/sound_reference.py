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
import threading
import wave
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from xml.sax.saxutils import escape

from sentence_reading.cache.paper_cache import project_root
from sentence_reading.llm.env import load_asr_env
from sentence_reading.llm.tts_speak_policy import speak_norm_version

# The break the stencil reading puts after every token, and the slack allowed
# around a mark when a sound is sorted into its window.
# What abandoning one sound of the straight reading costs, against the overlap a
# token gains by refusing it. A three-sound token gains 1 - 3/4 = 0.25 by
# refusing a fourth, so at 0.3 it takes the sound; a two-sound token gains
# 1 - 2/3 = 0.333 by refusing a third, so it still lets that one go. Two sounds
# is not enough evidence to force a third in. Free skips were the bug: the
# stencil comes from the token read alone, which is the less reliable reading.
SKIP_COST = 0.3
BREAK_MS = 100
PAD_MS = 25
BUILD_GIVE_UP = 5

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
    # Every number that changes the sounds is in the key, or GCS would keep
    # serving a reference built by an older rule. A design/386 reference kept
    # only the symbols over 30%, not how much each had, so it is a different one.
    from sentence_reading.llm.hear_waveform import SHARE_TAIL

    raw = (
        f"{speak_norm_version()}|{voice}|{BREAK_MS}|{PAD_MS}|{SKIP_COST}"
        f"|spread{SHARE_TAIL}|{spoken}"
    )
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


@lru_cache(maxsize=1)
def _voice_client():
    """One client for the life of the process, as the read-aloud path does.

    Building one discovers credentials and opens a gRPC channel. A reference
    build never closes it, so making a new one per build would leave a channel
    behind for every sentence the instance ever saw.
    """
    from google.cloud import texttospeech_v1beta1 as tts

    load_asr_env()
    return tts.TextToSpeechClient()


def synth_marked(ssml: str, voice: str) -> tuple[bytes, dict[str, float]]:
    """LINEAR16 at 16 kHz plus {mark name: seconds}.

    LINEAR16 so the audio decodes with the standard library and the reference
    build needs no ffmpeg. Timepoints are v1beta1 only.
    """
    from google.cloud import texttospeech_v1beta1 as tts

    client = _voice_client()
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


def hand_out(
    stencil: list[list[str]],
    natural: list[str],
    ranges: list[tuple[int, int]] | None = None,
) -> list[list[str]]:
    """Give the straight reading's sounds to the tokens, in order.

    Each token takes a run of the natural reading, the runs stay in order and do
    not overlap, and a sound may go to nobody. The score is how close a run is
    to that token's stencil, so a token ends up with the sounds it should own
    even though the widths differ between the two readings.

    Letting a sound go unclaimed is what keeps a punctuation-only token or a
    breath from bloating its neighbour, but it cannot be free. The stencil comes
    from the token read alone, and reading a word alone is the less reliable of
    the two: the model heard an isolated 	hin as \u00f0 \u025b n, so matching on
    identity alone dropped the real \u03b8 \u026a and left the word with one sound.
    A skip costs more than the best a better-fitting run could gain, so a sound
    is only ever abandoned when no token wants it at all.
    """
    from sentence_reading.llm.phone_match import overlap_ratio

    n, wide = len(stencil), len(natural)
    neg = float("-inf")
    best = [[neg] * (wide + 1) for _ in range(n + 1)]
    back: list[list[tuple[str, int] | None]] = [
        [None] * (wide + 1) for _ in range(n + 1)
    ]
    for j in range(wide + 1):
        best[0][j] = -SKIP_COST * j
        back[0][j] = ("skip", j - 1) if j else None
    for i in range(1, n + 1):
        want = stencil[i - 1]
        widest = len(want) + 2 if want else 0
        for j in range(wide + 1):
            if j and best[i][j - 1] - SKIP_COST > best[i][j]:
                best[i][j] = best[i][j - 1] - SKIP_COST
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
    if ranges is not None:
        ranges[:] = [(-1, -1)] * n
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
            if ranges is not None:
                ranges[i - 1] = (k, j)
            i, j = i - 1, k
    return out


def build(spoken: str, *, voice: str | None = None) -> dict[str, object]:
    """Two synthesis calls and two model passes. Call `reference_for` instead."""
    from sentence_reading.llm.hear_waveform import phone_frames, spread_text

    name = voice or reference_voice()
    straight, _t = synth_marked(f"<speak>{escape(spoken)}</speak>", name)
    pcm, _rate = pcm_of(straight)
    frames = phone_frames(pcm)
    natural = [str(one["sym"]) for one in frames]
    natural_share = [spread_text(list(one.get("share") or [])) for one in frames]

    ssml, spots = ssml_marked(spoken)
    marked, times = synth_marked(ssml, name)
    pcm2, rate2 = pcm_of(marked)
    stencil = cut_marks(
        phone_frames(pcm2), spots, times, len(pcm2) / float(rate2)
    )
    ranges: list[tuple[int, int]] = []
    given = hand_out(stencil, natural, ranges)
    words = []
    for i, (lo, hi, _tok) in enumerate(spots):
        a, b = ranges[i] if i < len(ranges) else (-1, -1)
        share_sounds = natural_share[a:b] if 0 <= a <= b else []
        words.append({
            "lo": lo,
            "hi": hi,
            "sounds": " ".join(given[i]),
            # design/388 — one native spread per sound, comma-separated,
            # `symbol=percent` pairs spaced inside it.
            "share": ",".join(share_sounds),
        })
    return {
        "voice": name,
        "words": words,
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
        share_bits: list[str] = []
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
                        share_bits.append(str(one.get("share") or "").strip())
        span["phone"] = " ".join(pieces)
        # design/388 — same sound order as phone, comma-separated. Empty when
        # this reference was built before the share was stored.
        joined = ",".join(share_bits)
        span["share"] = joined if any(bit.strip() for bit in share_bits) else ""
        if pieces:
            filled += 1
    return filled


def strip_ranges(spans: list[dict[str, int]]) -> None:
    """Drop the walk's bookkeeping before the spans go on the wire."""
    for span in spans:
        span.pop("spoken_lo", None)
        span.pop("spoken_hi", None)


def enabled() -> bool:
    """The kill switch. v1beta1 timepoints are a new API surface in production."""
    load_asr_env()
    return (os.environ.get("ASR_SOUND_REF") or "1").strip() not in ("0", "false")


# One build at a time. The model already serializes behind its own lock, so a
# second worker would only queue on it while holding a synthesis slot.
_PENDING: set[str] = set()
_PENDING_LOCK = threading.Lock()
_POOL: ThreadPoolExecutor | None = None
_BUILD_FAIL = ""
_BUILD_OK = 0
_BUILD_BAD = 0
_BUILD_RUN = 0
_BUILD_STATUS = 0


def _pool() -> ThreadPoolExecutor:
    global _POOL
    if _POOL is None:
        _POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="soundref")
    return _POOL


def _run_build(spoken: str, voice: str, key: str) -> None:
    global _BUILD_FAIL, _BUILD_OK, _BUILD_BAD, _BUILD_RUN, _BUILD_STATUS
    try:
        _write_cache(key, build(spoken, voice=voice))
        _BUILD_OK += 1
        _BUILD_FAIL = ""
        _BUILD_RUN = 0
        _BUILD_STATUS = 0
    except Exception as exc:  # noqa: BLE001
        # A failed build must not take the request down with it. The next call
        # finds the cache still empty and asks again.
        _BUILD_BAD += 1
        _BUILD_RUN += 1
        _BUILD_FAIL = re.sub(r"[^a-z0-9]+", "_", type(exc).__name__.lower())[:40]
        # The class name alone cannot tell a voice we are not allowed to use from
        # an SSML we built wrong. The status number can, and unlike the message it
        # cannot carry a line of the paper into the evidence stream.
        status = getattr(exc, "code", None)
        _BUILD_STATUS = status if isinstance(status, int) else 0
    finally:
        with _PENDING_LOCK:
            _PENDING.discard(key)


def request_build(spoken: str, *, voice: str | None = None) -> str:
    """Ask for a reference in the background. Never blocks, never raises.

    A build costs two synthesis calls and two model passes, about eight seconds,
    which is far too long to hold a screen on. So the request path serves what is
    cached and asks for what is not, and the reading after this one scores.
    """
    text = (spoken or "").strip()
    if not text:
        return "empty"
    if not enabled():
        return "off"
    # A build that fails costs a synthesis call, so a voice we are not allowed to
    # use would bill us once for every sentence anyone ever opens. After a few
    # failures in a row, stop asking until a success or a restart clears it.
    if _BUILD_RUN >= BUILD_GIVE_UP:
        return "sunk"
    key = cache_key(text, voice or reference_voice())
    with _PENDING_LOCK:
        if key in _PENDING:
            return "building"
        _PENDING.add(key)
    try:
        _pool().submit(_run_build, text, voice or reference_voice(), key)
    except RuntimeError:
        with _PENDING_LOCK:
            _PENDING.discard(key)
        return "busy"
    return "queued"


# design/378 - how long a whole paper's warm may run, and how long it waits for
# the reader's own build to clear. A paper is a few hundred sentences at twenty
# seconds each, so the cap is in hours, not minutes; it exists so a thread cannot
# outlive the thing it was warming.
WARM_BUDGET_S = 3 * 60 * 60
WARM_POLL_S = 0.5
WARM_WAIT_S = 120.0


def _pending_n() -> int:
    with _PENDING_LOCK:
        return len(_PENDING)


def warm_paper(lines: list[str], *, voice: str | None = None) -> dict[str, int]:
    """Build every reference this paper will need, one at a time, yielding.

    The reader must never wait behind this. There is one build worker, so handing
    it three hundred sentences at once would put the sentence actually on screen
    three hundred places back -- worse than building nothing. So this submits one
    and waits for the queue to clear before submitting the next: a reader's own
    request lands behind at most one build in flight rather than behind the paper.

    Blocking is the point, so call it on a thread. It never raises.
    """
    done = ready = failed = skipped = 0
    if not enabled():
        return {"warm_n": 0, "warm_off": 1}
    started = time.monotonic()
    for text in lines:
        line = (text or "").strip()
        if not line:
            continue
        if time.monotonic() - started > WARM_BUDGET_S:
            skipped += 1
            continue
        # Repeated failures already stop `request_build`; stop walking too, or a
        # paper's worth of sentences each cost a synthesis call to learn that.
        if _BUILD_RUN >= BUILD_GIVE_UP:
            skipped += 1
            continue
        try:
            if reference_for(line, voice=voice, allow_build=False) is not None:
                ready += 1
                continue
        except Exception:  # noqa: BLE001
            pass
        # Yield to whatever the reader asked for.
        waited = 0.0
        while _pending_n() > 0 and waited < WARM_WAIT_S:
            time.sleep(WARM_POLL_S)
            waited += WARM_POLL_S
        code = request_build(line, voice=voice)
        if code in ("queued", "building"):
            done += 1
        else:
            failed += 1
        # And wait for it, so the next submission does not stack.
        waited = 0.0
        while _pending_n() > 0 and waited < WARM_WAIT_S:
            time.sleep(WARM_POLL_S)
            waited += WARM_POLL_S
    return {
        "warm_n": len(lines),
        "warm_built": done,
        "warm_ready": ready,
        "warm_failed": failed,
        "warm_skipped": skipped,
    }


def build_report() -> dict[str, object]:
    """Counts for the evidence row, so a silent failure is visible."""
    with _PENDING_LOCK:
        waiting = len(_PENDING)
    return {
        "sound_ref_on": 1 if enabled() else 0,
        "sound_ref_ok": _BUILD_OK,
        "sound_ref_bad": _BUILD_BAD,
        "sound_ref_waiting": waiting,
        "sound_ref_fail": _BUILD_FAIL or "none",
        "sound_ref_run": _BUILD_RUN,
        "sound_ref_status": _BUILD_STATUS,
    }
