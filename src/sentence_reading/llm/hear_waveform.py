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

# Total convolution stride is 320 samples at 16 kHz, so a frame is 20 ms. The
# reference cut needs this to turn a mark time into a frame number.
FRAME_MS = 20
# design/386 — a native sound keeps every symbol at or above this share of the
# softmax, blank left out. The reader's sound matches only when it clears the
# same line on every one of them. 0.30 is the owner's number; it is in the
# reference cache key so an older reference is not scored as if it knew this.
SHARE_MIN = 0.30
_FRAME_READY = False
_EXTRACTOR = None
_INV: dict[int, str] = {}
_PAD = 0


def hear_phones(data: bytes) -> str:
    """Space-separated phones from the recording. Empty when the model cannot run."""
    phones, _report = hear_phones_report(data)
    return phones


def hear_phones_report(data: bytes) -> tuple[str, dict[str, object]]:
    """Phones plus a short code for the step that stopped, for the evidence row."""
    phones, _sheet, report = _hear(data, want_sheet=False)
    return phones, report


def hear_phones_sheet(
    data: bytes,
) -> tuple[str, object | None, dict[str, object]]:
    """design/381 - the same single model pass, plus the probabilities.

    The sheet is one row per 20 ms frame and one column per sound, log-softmaxed.
    `argmax` throws it away, and design/380 measured what that costs: a sound the
    model guessed at 0.35 counted against the reader exactly as hard as one it was
    0.97 sure of. Scoring by certainty needs the sheet, and running the model a
    second time to get it would double the wait on every take.
    """
    return _hear(data, want_sheet=True)


def _hear(
    data: bytes, *, want_sheet: bool
) -> tuple[str, object | None, dict[str, object]]:
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
        return "", None, report
    if not report["ffmpeg"]:
        report["hear_code"] = "ffmpeg_missing"
        return "", None, report

    clock = time.monotonic()
    try:
        pcm = _pcm16k(data)
    except _DecodeError as exc:
        report["hear_code"] = "decode_failed"
        report["hear_detail"] = _snake(str(exc))
        report["decode_ms"] = int((time.monotonic() - clock) * 1000)
        return "", None, report
    except (OSError, subprocess.TimeoutExpired) as exc:
        report["hear_code"] = "decode_crashed"
        report["hear_detail"] = _snake(type(exc).__name__)
        report["decode_ms"] = int((time.monotonic() - clock) * 1000)
        return "", None, report
    report["decode_ms"] = int((time.monotonic() - clock) * 1000)
    if pcm is None:
        report["hear_code"] = "decode_empty"
        return "", None, report
    report["pcm_n"] = int(pcm.shape[0])
    if int(pcm.shape[0]) < 1600:
        report["hear_code"] = "too_short"
        return "", None, report

    clock = time.monotonic()
    try:
        _load()
    except Exception as exc:  # noqa: BLE001
        report["hear_code"] = "load_failed"
        report["hear_detail"] = _snake(type(exc).__name__)
        report["load_ms"] = int((time.monotonic() - clock) * 1000)
        return "", None, report
    report["load_ms"] = int((time.monotonic() - clock) * 1000)
    if _PROCESSOR is None or _MODEL is None:
        report["hear_code"] = "model_missing"
        report["hear_detail"] = _snake(_LOAD_FAIL or "none")
        return "", None, report

    import torch

    clock = time.monotonic()
    sheet = None
    try:
        with _LOCK:
            values = _PROCESSOR(
                pcm, sampling_rate=16000, return_tensors="pt"
            ).input_values
            with torch.no_grad():
                logits = _MODEL(values).logits
            ids = torch.argmax(logits, dim=-1)
            text = _PROCESSOR.batch_decode(ids)[0]
            # design/381 - the same logits, before they are thrown away.
            if want_sheet:
                sheet = torch.log_softmax(logits, dim=-1)[0]
    except Exception as exc:  # noqa: BLE001
        report["hear_code"] = "infer_failed"
        report["hear_detail"] = _snake(type(exc).__name__)
        report["infer_ms"] = int((time.monotonic() - clock) * 1000)
        return "", None, report
    report["infer_ms"] = int((time.monotonic() - clock) * 1000)
    out = " ".join(str(text).split())
    report["phone_n"] = len(out.split())
    if not out:
        report["hear_code"] = "empty_text"
    return out, sheet, report


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


def _load_frames() -> None:
    """The model and its symbol table, without the tokenizer.

    `Wav2Vec2Processor` builds a phoneme tokenizer that wants eSpeak on the box,
    and its `batch_decode` throws away the frame each symbol landed on. The
    reference cut needs those frames, so the symbol table is read out of
    `vocab.json` instead. The collapse below is the library's own: group runs of
    one id, drop the blank. This vocab has no word delimiter, so the two paths
    produce the same symbols in the same order.
    """
    global _FRAME_READY, _EXTRACTOR, _INV, _PAD
    if _FRAME_READY:
        return
    with _LOCK:
        if _FRAME_READY:
            return
        import json as _json
        import pathlib as _pathlib

        from huggingface_hub import hf_hub_download
        from transformers import Wav2Vec2FeatureExtractor

        def _file(name: str) -> str:
            # The image prefetches these at build time, so the cache holds them.
            # Asking the hub first would add a network round trip to the first
            # take of every cold instance and fail closed if egress is blocked.
            try:
                return hf_hub_download(_NAME, name, local_files_only=True)
            except Exception:  # noqa: BLE001
                return hf_hub_download(_NAME, name)

        try:
            _EXTRACTOR = Wav2Vec2FeatureExtractor.from_pretrained(
                _NAME, local_files_only=True
            )
        except Exception:  # noqa: BLE001
            _EXTRACTOR = Wav2Vec2FeatureExtractor.from_pretrained(_NAME)
        vocab = _json.loads(
            _pathlib.Path(_file("vocab.json")).read_text(encoding="utf-8")
        )
        cfg = _json.loads(
            _pathlib.Path(_file("tokenizer_config.json")).read_text(
                encoding="utf-8"
            )
        )
        _INV = {int(i): s for s, i in vocab.items()}
        _PAD = int(vocab[str(cfg.get("pad_token") or "<pad>")])
        _FRAME_READY = True


def _load_ctc() -> None:
    """Only the acoustic model. The text path's processor is not needed here."""
    global _READY, _MODEL, _LOAD_FAIL
    if _MODEL is not None:
        return
    with _LOCK:
        if _MODEL is not None:
            return
        try:
            from transformers import Wav2Vec2ForCTC

            try:
                _MODEL = Wav2Vec2ForCTC.from_pretrained(
                    _NAME, local_files_only=True
                )
            except Exception:  # noqa: BLE001
                _MODEL = Wav2Vec2ForCTC.from_pretrained(_NAME)
            _MODEL.eval()
        except Exception as exc:  # noqa: BLE001
            _LOAD_FAIL = type(exc).__name__
            _MODEL = None
            raise
        _LOAD_FAIL = ""


def phone_frames(pcm) -> list[dict[str, object]]:
    """Each symbol the model emits, with the frames it was emitted on.

    `pcm` is mono float32 at 16 kHz. `f0` and `f1` are frame numbers; multiply
    by `FRAME_MS` for milliseconds.
    """
    from itertools import groupby

    import torch

    _load_frames()
    _load_ctc()
    if _MODEL is None or _EXTRACTOR is None:
        return []
    with _LOCK:
        values = _EXTRACTOR(
            pcm, sampling_rate=16000, return_tensors="pt"
        ).input_values
        with torch.no_grad():
            logits = _MODEL(values).logits[0]
        probs = torch.softmax(logits, dim=-1)
        ids = logits.argmax(dim=-1).tolist()
    out: list[dict[str, object]] = []
    frame = 0
    for tid, group in groupby(ids):
        n = sum(1 for _ in group)
        f0, frame = frame, frame + n
        if tid == _PAD:
            continue
        sym = _INV.get(int(tid), "")
        if not sym:
            continue
        # design/386 — every symbol this stretch gives at least SHARE_MIN,
        # blank excluded. The winner alone cannot say the native was split.
        avg = probs[f0:frame].mean(dim=0)
        hot: list[tuple[float, str]] = []
        for i, name in _INV.items():
            if i == _PAD or not name:
                continue
            p = float(avg[i])
            if p >= SHARE_MIN:
                hot.append((p, name))
        hot.sort(reverse=True)
        out.append({
            "sym": sym,
            "f0": f0,
            "f1": frame,
            "share": [name for _p, name in hot],
        })
    return out


def phones_of(frames: list[dict[str, object]]) -> str:
    """The same space-joined string the text path returns."""
    return " ".join(str(one["sym"]) for one in frames)


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


def _said_between(top: list[int], lo: int, hi: int) -> int:
    """How many sounds the model reads off the audio there, CTC's own count.

    Collapse repeats, drop the blank. The whole vocabulary is in play on purpose:
    a sound the reference does not contain is exactly the sound this counts.
    """
    seen = 0
    last = -1
    for t in range(max(0, lo), min(len(top), hi)):
        now = top[t]
        if now != last and now != _PAD:
            seen += 1
        last = now
    return seen


def _mean_prob(sheet: object, tid: int, lo: int, hi: int) -> float:
    """Mean probability of one symbol over frames [lo, hi). The sheet is log-softmax."""
    import math

    col = [row[0] for row in sheet[:, [tid]].tolist()]
    if hi <= lo:
        return 0.0
    total = 0.0
    n = 0
    for t in range(max(0, lo), min(hi, len(col))):
        total += math.exp(col[t])
        n += 1
    return total / n if n else 0.0


def parse_share_groups(
    raw: str, groups: list[list[str]]
) -> list[list[list[str]]] | None:
    """design/386 — one required-symbol list per reference sound.

    Words are barred apart, the same way `target_phones` is. Sounds inside a
    word are comma-separated, symbols inside a sound are spaced. A sound with
    no symbol at SHARE_MIN is an empty slot, and that sound cannot match.
    A row that does not have one slot per reference sound is refused whole.
    """
    parts = [one.strip() for one in (raw or "").split("|")]
    if len(parts) != len(groups):
        return None
    out: list[list[list[str]]] = []
    for part, group in zip(parts, groups):
        slots = part.split(",") if part else []
        if len(slots) != len(group):
            return None
        out.append([slot.split() for slot in slots])
    return out


def sound_score_of(
    sheet: object,
    groups: list[list[str]],
    shares: list[list[list[str]]] | None = None,
) -> list[dict[str, float | list[float]] | None] | None:
    """design/382·386 — matches over the longer of the two sides.

    A reference sound matches when every symbol the native reading kept at
    SHARE_MIN or above is also at SHARE_MIN on the reader, in the frames that
    sound landed on. Blank is not a symbol. Without a share row, each stored
    symbol is its own required set: that is an older reference, which only
    kept the winner.

    The divisor is the longer of the reference and what the reader actually
    said, so a reader who says every reference sound and then one more scores
    n/(n+1) rather than n/n.

    One entry per word in the order given, `None` for a word with no sound the
    model knows -- the same thing `phoneOverlap` means by -1.

    No boundary is decided here (design/371). The words were cut by the builder
    from Google's marks; frame times only sort the reader's sounds into those
    windows, which is the allowed direction.
    """
    from sentence_reading.llm.sound_align import align

    if sheet is None or not groups:
        return None
    _load_frames()
    if not _INV:
        return None
    ids = {sym: tid for tid, sym in _INV.items()}
    as_ids = [[ids[s] for s in group if s in ids] for group in groups]
    wanted = sorted({tid for group in as_ids for tid in group} | {_PAD})
    if len(wanted) <= 1:
        return None
    column = {tid: i for i, tid in enumerate(wanted)}
    flat: list[int] = []
    owner: list[int] = []
    # None means this reference has no share row, so the stored symbol is the
    # whole of what the sound requires. An empty list means the native sound
    # kept nothing at SHARE_MIN, and that sound does not match.
    req_for: list[tuple[str, list[str] | None]] = []
    for i, group in enumerate(groups):
        word_share = shares[i] if shares is not None and i < len(shares) else None
        slot_i = 0
        for sym in group:
            slot = (
                word_share[slot_i]
                if word_share is not None and slot_i < len(word_share)
                else None
            )
            slot_i += 1
            if sym not in ids:
                continue
            flat.append(column[ids[sym]])
            owner.append(i)
            req_for.append((sym, slot))
    try:
        # Only the columns this sentence can use, for the alignment -- the full
        # sheet is hundreds of frames by four hundred sounds and Python walks it
        # far slower than the model pass that produced it. The free reading needs
        # every column, so torch takes that argmax, not this.
        rows = sheet[:, wanted].tolist()
        top = [int(v) for v in sheet.argmax(dim=-1).tolist()]
    except Exception:  # noqa: BLE001
        return None
    spans = align(rows, flat, blank=column[_PAD])
    if spans is None:
        return None
    mine = [[k for k, w in enumerate(owner) if w == i]
            for i in range(len(groups))]
    out: list[dict[str, float | list[float]] | None] = []
    for i, keys in enumerate(mine):
        if not keys:
            out.append(None)
            continue
        lo = spans[keys[0]][0]
        if i + 1 >= len(mine):
            # Past the last word, the recording's own end: anything after the
            # final reference sound belongs to the final word and nowhere else.
            hi = len(top)
        elif mine[i + 1]:
            # design/382 - to where the next word's first sound starts, not to
            # where this word's last sound was emitted. A sound the reader added
            # after the reference ran out sits in the gap between the two, and a
            # window that stops at the reference's last sound cannot see it.
            hi = max(spans[keys[-1]][1], spans[mine[i + 1][0]][0])
        else:
            # The next word has no reference, so there is no boundary to stop at.
            # Widening here would charge this word for that word's audio.
            hi = spans[keys[-1]][1]
        said = _said_between(top, lo, hi)
        flags: list[float] = []
        # design/387 — the lowest required symbol, not a 0/1. The phone applies
        # the difficulty bar and then the account line. Folding either in here
        # would bake one rung's leniency into the number the line learns from.
        raws: list[float] = []
        for k in keys:
            sym, slot = req_for[k]
            req = [sym] if slot is None else slot
            lo_s, hi_s = spans[k][0], spans[k][1]
            probs = []
            for one in req:
                tid = ids.get(one)
                probs.append(0.0 if tid is None else _mean_prob(sheet, tid, lo_s, hi_s))
            low = min(probs) if probs else 0.0
            raws.append(low)
            flags.append(1.0 if probs and low >= SHARE_MIN else 0.0)
        n = len(flags)
        mean = sum(flags) / n
        out.append({
            "sure": mean,
            "low": min(flags),
            "n": float(n),
            "said": float(said),
            "sym": mean * n / max(n, said),
            "each": raws,
        })
    return out


def certainty_of(
    sheet: object, groups: list[list[str]]
) -> list[list[float]] | None:
    """design/381 - how sure the model is about each word's reference sounds.

    `groups` is one list of the model's own symbols per printed word, which is
    exactly what the reference builder stored. The answer is one list of
    certainties per word in the same order, empty for a word with no sound the
    model knows -- the same thing today's `-1` from `phoneOverlap` means.

    Every sound comes back rather than the word's average, because a word can
    average well while holding one sound that is simply not there.

    No boundary is decided here (design/371). The words were already cut by the
    builder from Google's marks; this only asks where each sound landed.
    """
    from sentence_reading.llm.sound_align import certainty_by_group

    if sheet is None or not groups:
        return None
    _load_frames()
    if not _INV:
        return None
    ids = {sym: tid for tid, sym in _INV.items()}
    as_ids = [[ids[s] for s in group if s in ids] for group in groups]
    wanted = sorted({tid for group in as_ids for tid in group} | {_PAD})
    if len(wanted) <= 1:
        return None
    # Only the columns this sentence can use. The full sheet is hundreds of frames
    # by four hundred sounds, and walking that from Python one cell at a time is
    # far slower than the model pass that produced it.
    column = {tid: i for i, tid in enumerate(wanted)}
    try:
        rows = sheet[:, wanted].tolist()
    except Exception:  # noqa: BLE001
        return None
    return certainty_by_group(
        rows,
        [[column[tid] for tid in group] for group in as_ids],
        blank=column[_PAD],
    )
