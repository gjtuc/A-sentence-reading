"""
무엇을: 음성 질문 녹음 → Gemini 받아쓰기 (design/475).
왜: 사용자는 화면의 영어 문장에 대해 한국어와 영어를 섞어 묻는다. 문장을 함께
주면 전문 용어를 문장에 쓰인 철자대로 적을 수 있다.
"""

from __future__ import annotations

import concurrent.futures
import time
from dataclasses import dataclass

from sentence_reading.llm.env import gemini_api_key, gemini_model

# About three minutes of AAC at 128 kbps is 3 MB; WebM/Opus is smaller.
MAX_AUDIO_BYTES = 12 * 1024 * 1024
MAX_SENTENCE_CHARS = 2000
_TIMEOUT_S = 60.0

_SYSTEM = """You write down a spoken question. A Korean reader is looking at one
English sentence from a scientific paper and asks something about it, out loud.
The speaker mixes Korean and English freely.

Rules:
- Write Korean in Hangul and English words in English. A word that appears in the
  sentence is spelled exactly as in the sentence.
- Drop fillers and false starts (음, 어, 그, 저기, uh, um, a word said twice by
  mistake). Keep the speaker's own wording and order otherwise.
- Do not answer, explain, translate, summarise or add anything.
- Output the question only, as plain text on one line. No quotes, no labels.
- If nothing intelligible was said, output nothing."""

# design/490 - the same recording path, for a title the reader dictates.
_SYSTEM_TITLE = """You write down a document title a Korean reader dictates for a
card in their library. The speaker mixes Korean and English freely.

Rules:
- Write Korean in Hangul and English words in English. A word that appears in the
  current title is spelled exactly as there.
- Drop fillers and false starts (음, 어, 그, 저기, uh, um, a word said twice by
  mistake). Keep the speaker's own wording and order otherwise.
- Do not answer, explain, translate, summarise or add anything.
- Output the title only, as plain text on one line. No quotes, no labels, no
  closing period.
- If nothing intelligible was said, output nothing."""

PURPOSES = ("question", "title")


@dataclass
class VoiceQuestion:
    text: str
    code: str
    ms: int


def _clean(text: str) -> str:
    one = " ".join((text or "").split())
    if len(one) >= 2 and one[0] == one[-1] and one[0] in "\"'“”":
        one = one[1:-1].strip()
    return one


def _call(audio: bytes, mime: str, sentence: str, purpose: str = "question") -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=gemini_api_key())
    if purpose == "title":
        system = _SYSTEM_TITLE
        user = (
            "The current title:\n"
            f"{sentence.strip() or '(none)'}\n\n"
            "Write down the title in the recording."
        )
    else:
        system = _SYSTEM
        user = (
            "The sentence on the reader's screen:\n"
            f"{sentence.strip() or '(none)'}\n\n"
            "Write down the question in the recording."
        )
    extra: dict = {}
    thinking = getattr(types, "ThinkingConfig", None)
    if thinking is not None:
        # The question is short and the words are heard, not reasoned out.
        extra["thinking_config"] = thinking(thinking_budget=0)
    response = client.models.generate_content(
        model=gemini_model(),
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=user),
                    types.Part.from_bytes(data=audio, mime_type=mime),
                ],
            )
        ],
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.0,
            max_output_tokens=1024,
            **extra,
        ),
    )
    try:
        from sentence_reading.llm.usage_meter import record_gemini_response

        record_gemini_response(f"{system}\n{user}", response)
    except Exception:  # noqa: BLE001
        pass
    text = getattr(response, "text", None) or ""
    if text:
        return text
    parts: list[str] = []
    for cand in getattr(response, "candidates", None) or []:
        content = getattr(cand, "content", None)
        for part in getattr(content, "parts", None) or []:
            if getattr(part, "thought", False):
                continue
            parts.append(getattr(part, "text", None) or "")
    return "".join(parts)


def audio_mime(raw: str) -> str:
    m = (raw or "").split(";")[0].strip().lower()
    if "webm" in m:
        return "audio/webm"
    if "ogg" in m:
        return "audio/ogg"
    if "wav" in m:
        return "audio/wav"
    return "audio/mp4"


def transcribe_question(
    audio: bytes, *, mime: str, sentence: str, purpose: str = "question"
) -> VoiceQuestion:
    """Never raises. An empty text with code ``ok`` means nothing was said."""
    start = time.monotonic()

    def done(text: str, code: str) -> VoiceQuestion:
        return VoiceQuestion(text, code, int((time.monotonic() - start) * 1000))

    if not audio:
        return done("", "empty_audio")
    if len(audio) > MAX_AUDIO_BYTES:
        return done("", "audio_too_large")
    if not gemini_api_key():
        return done("", "gemini_key_missing")
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        args = [audio, audio_mime(mime), (sentence or "")[:MAX_SENTENCE_CHARS]]
        if purpose == "title":
            args.append("title")
        fut = pool.submit(_call, *args)
        try:
            raw = fut.result(timeout=_TIMEOUT_S)
        except concurrent.futures.TimeoutError:
            return done("", "timeout")
        except Exception as exc:  # noqa: BLE001
            return done("", f"call_failed_{type(exc).__name__.lower()}"[:60])
    text = _clean(raw)
    if purpose == "title":
        text = text.rstrip(".。")
    return done(text, "ok")
