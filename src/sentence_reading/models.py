"""
무엇을: 세션·그림·문장 데이터 형태.
왜: UI와 PDF 층이 같은 계약을 보게 하고, 인덱스 독립 불변조건을 코드에 고정한다.
다음에: 디스크 직렬화, caption/page 메타 보강.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Figure:
    """논문에서 추출한 그림 한 장 (또는 플레이스홀더)."""

    id: str
    # WHY: 스켈레톤은 data URL / 정적 경로 문자열. 나중엔 bytes + mime.
    image_src: str
    caption: str = ""
    page_index: int | None = None


@dataclass(frozen=True)
class Sentence:
    """본문에서 잘라 낸 문장 하나 — UI 아래 패널의 유일한 표시 단위."""

    id: str
    text: str
    # NOTE: 원문 오프셋은 하이라이트/검증용. stub에선 생략 가능.
    start_char: int | None = None
    end_char: int | None = None


@dataclass
class PaperSession:
    """
    한 PDF(또는 mock)에 대한 읽기 세션.

    INVARIANT: figure_index 변경은 sentence_index를 바꾸지 않는다.
    INVARIANT: sentence_index 변경은 figure_index를 바꾸지 않는다.
    """

    title: str
    figures: list[Figure] = field(default_factory=list)
    sentences: list[Sentence] = field(default_factory=list)
    figure_index: int = 0
    sentence_index: int = 0

    def clamp_indices(self) -> None:
        """빈 목록이면 인덱스를 0으로 두고, UI가 empty 상태를 처리한다."""
        if self.figures:
            self.figure_index = max(0, min(self.figure_index, len(self.figures) - 1))
        else:
            self.figure_index = 0
        if self.sentences:
            self.sentence_index = max(0, min(self.sentence_index, len(self.sentences) - 1))
        else:
            self.sentence_index = 0

    def advance_figure(self, delta: int) -> None:
        # INVARIANT: 문장 인덱스는 건드리지 않음 — 수동 동기화 제품 핵심.
        if not self.figures:
            return
        self.figure_index = (self.figure_index + delta) % len(self.figures)

    def advance_sentence(self, delta: int) -> None:
        # INVARIANT: 그림 인덱스는 건드리지 않음.
        if not self.sentences:
            return
        self.sentence_index = (self.sentence_index + delta) % len(self.sentences)

    def current_figure(self) -> Figure | None:
        if not self.figures:
            return None
        return self.figures[self.figure_index]

    def current_sentence(self) -> Sentence | None:
        if not self.sentences:
            return None
        return self.sentences[self.sentence_index]

    def to_public_dict(self) -> dict:
        """API/프론트용 스냅샷."""
        fig = self.current_figure()
        sent = self.current_sentence()
        return {
            "title": self.title,
            "figure_index": self.figure_index,
            "figure_count": len(self.figures),
            "sentence_index": self.sentence_index,
            "sentence_count": len(self.sentences),
            "figure": None
            if fig is None
            else {
                "id": fig.id,
                "image_src": fig.image_src,
                "caption": fig.caption,
                "page_index": fig.page_index,
            },
            "sentence": None
            if sent is None
            else {"id": sent.id, "text": sent.text},
            "figures": [
                {"id": f.id, "image_src": f.image_src, "caption": f.caption}
                for f in self.figures
            ],
            "sentences": [{"id": s.id, "text": s.text} for s in self.sentences],
        }


def build_mock_session() -> PaperSession:
    """
    WHY: PDF stub 전에 UI·네비·타이포를 검증할 고정 데이터.
    그림은 SVG data URL 플레이스홀더.
    """

    def _svg(label: str, fill: str) -> str:
        # WHY: viewBox만 두고 CSS가 키울 수 있게 — fixed width면 확대 안 됨
        svg = (
            f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 640 360' "
            f"preserveAspectRatio='xMidYMid meet'>"
            f"<rect width='100%' height='100%' fill='{fill}'/>"
            f"<text x='50%' y='50%' dominant-baseline='middle' text-anchor='middle' "
            f"fill='#f2f2f2' font-size='36' font-family='Segoe UI, sans-serif'>{label}</text>"
            f"</svg>"
        )
        from urllib.parse import quote

        return "data:image/svg+xml," + quote(svg)

    figures = [
        Figure(id="fig-1", image_src=_svg("Figure 1 (mock)", "#1a3a4a"), caption="Fig. 1 — mock catalyst scheme"),
        Figure(id="fig-2", image_src=_svg("Figure 2 (mock)", "#3a1a4a"), caption="Fig. 2 — mock XRD pattern"),
        Figure(id="fig-3", image_src=_svg("Figure 3 (mock)", "#1a4a2a"), caption="Fig. 3 — mock activity plot"),
    ]
    sentences = [
        Sentence(id="s-1", text="Ni catalyst was a convenient material for the model reaction."),
        Sentence(
            id="s-2",
            text="As shown in Figure 1, the active sites remain stable after pretreatment.",
        ),
        Sentence(
            id="s-3",
            text="We then examined the diffraction pattern; see Figure 2 for the main peaks.",
        ),
        Sentence(
            id="s-4",
            text="Activity increased linearly with metal loading under the tested conditions.",
        ),
        Sentence(
            id="s-5",
            text="These results suggest that sentence-level rereading helps keep the claim in view.",
        ),
    ]
    return PaperSession(title="Mock paper (skeleton)", figures=figures, sentences=sentences)
