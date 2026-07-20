"""
무엇을: 원문 문자열 → Sentence 리스트.
왜: UI 단위는 페이지/단락이 아니라 **한 문장**이다.
다음에: pysbd 등 + 논문 약어 예외 테스트.
"""

from __future__ import annotations

from sentence_reading.models import Sentence


def split_into_sentences(raw_text: str) -> list[Sentence]:
    """
    원문을 문장 단위로 나눈다.

    # WHY: 정규식 `\\. ` 만 쓰면 Fig. / et al. / i.e. / e.g. 에서 잘못 끊긴다.
    # NEXT: pysbd (또는 유사) + 학술 약어 화이트리스트 테스트 픽스처.
    # NOTE: 수식·캡션을 본문 문장과 섞지 않도록 extract 단계에서 분리하는 편이 낫다.
    """
    raise NotImplementedError(
        "Sentence splitting is stubbed. Use mock session for UI. "
        f"Received {len(raw_text)} chars of text."
    )
