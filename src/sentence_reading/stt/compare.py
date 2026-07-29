"""
무엇을: 영문 원문 vs STT 인식 결과 단어 diff (점수 없음).
왜: 발음 연습은 ‘차이 보기’만 — AI 채점 금지 (design/37).
다음에: 서버 STT 오디오 경로.
"""

from __future__ import annotations

import re
from typing import Any


_TAG_RE = re.compile(r"<[^>]+>")
_PUNCT_RE = re.compile(r"[^\w\s']+", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")


def normalize_en(text: str | None) -> str:
    """비교용 정규화. None/비문자도 빈 문자열."""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    t = _TAG_RE.sub(" ", text)
    t = t.lower().replace("\u2019", "'").replace("\u2018", "'")
    t = _PUNCT_RE.sub(" ", t)
    t = _SPACE_RE.sub(" ", t).strip()
    return t


def tokenize_en(text: str | None) -> list[str]:
    n = normalize_en(text)
    if not n:
        return []
    return n.split(" ")


def diff_tokens(expected: str | None, heard: str | None) -> dict[str, Any]:
    """
    Myers 유사 LCS 기반 단어 op 목록.
    # INVARIANT: score / grade / accuracy 키를 절대 넣지 않는다.
    """
    if expected is not None and not isinstance(expected, str):
        return {"ok": False, "error": "invalid_expected"}
    if heard is not None and not isinstance(heard, str):
        return {"ok": False, "error": "invalid_heard"}

    exp = tokenize_en(expected)
    hrd = tokenize_en(heard)
    if not exp and not hrd:
        return {"ok": False, "error": "empty"}

    # WHY: 고전 DP LCS — 문장 단위라 토큰 수 작음 (한도 아래에서 충분)
    n, m = len(exp), len(hrd)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if exp[i - 1] == hrd[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    diff: list[dict[str, Any]] = []
    i, j = n, m
    stack: list[dict[str, Any]] = []
    while i > 0 or j > 0:
        if i > 0 and j > 0 and exp[i - 1] == hrd[j - 1]:
            stack.append(
                {"op": "equal", "expected": exp[i - 1], "heard": hrd[j - 1]}
            )
            i -= 1
            j -= 1
        elif j > 0 and (i == 0 or dp[i][j - 1] >= dp[i - 1][j]):
            stack.append({"op": "insert", "expected": None, "heard": hrd[j - 1]})
            j -= 1
        else:
            stack.append({"op": "delete", "expected": exp[i - 1], "heard": None})
            i -= 1

    # WHY: 인접 delete+insert → replace 로 묶어 읽기 쉽게
    k = 0
    rev = list(reversed(stack))
    while k < len(rev):
        cur = rev[k]
        if (
            cur["op"] == "delete"
            and k + 1 < len(rev)
            and rev[k + 1]["op"] == "insert"
        ):
            diff.append(
                {
                    "op": "replace",
                    "expected": cur["expected"],
                    "heard": rev[k + 1]["heard"],
                }
            )
            k += 2
            continue
        if (
            cur["op"] == "insert"
            and k + 1 < len(rev)
            and rev[k + 1]["op"] == "delete"
        ):
            diff.append(
                {
                    "op": "replace",
                    "expected": rev[k + 1]["expected"],
                    "heard": cur["heard"],
                }
            )
            k += 2
            continue
        diff.append(cur)
        k += 1

    return {
        "ok": True,
        "expected_tokens": exp,
        "heard_tokens": hrd,
        "diff": diff,
    }
