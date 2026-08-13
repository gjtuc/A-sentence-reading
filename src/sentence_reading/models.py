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
    # WHY: design/40 — ingest 시 캡션 번역
    caption_ko: str = ""
    # WHY: design/45 — 캡션 번역 단계 (draft|sense|polish|harmonize)
    caption_ko_stage: str = ""


@dataclass(frozen=True)
class Sentence:
    """본문에서 잘라 낸 문장 하나 — UI 패널의 유일한 표시 단위."""

    id: str
    text: str
    # NOTE: 원문 오프셋은 하이라이트/검증용. stub에선 생략 가능.
    start_char: int | None = None
    end_char: int | None = None
    # WHY: Gemini 정제 후 title / abstract / body 구분 (네비는 단일 리스트)
    section: str | None = None
    # WHY: design/40 — ingest 시 섹션 파이프+요지 재감수 결과
    text_ko: str = ""
    # WHY: design/45 — draft|sense|polish|harmonize (빈 문자열 = 미번역)
    text_ko_stage: str = ""


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
    # WHY: design/40 — 섹션별 번역 정리본 {section: {en, ko}}
    translate_digests: dict = field(default_factory=dict)
    # WHY: design/41 — References [{n, text, doi}]
    references: list = field(default_factory=list)

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

    def to_public_dict(self, *, include_images: bool = True) -> dict:
        """API/프론트용 스냅샷.

        design/129 — ``include_images=False`` omits PNG data-URLs so /open stays
        small; clients fetch a ±1 window via ``/figures/window``.
        """
        fig = self.current_figure()
        sent = self.current_sentence()

        def _fig_public(f: Figure) -> dict:
            return {
                "id": f.id,
                # WHY: empty string = stub; never invent a fake placeholder image.
                "image_src": f.image_src if include_images else "",
                "caption": f.caption,
                "caption_ko": f.caption_ko or "",
                "caption_ko_stage": f.caption_ko_stage or "",
                "page_index": f.page_index,
            }

        return {
            "title": self.title,
            "figure_index": self.figure_index,
            "figure_count": len(self.figures),
            "sentence_index": self.sentence_index,
            "sentence_count": len(self.sentences),
            "figure": None if fig is None else _fig_public(fig),
            "sentence": None
            if sent is None
            else {
                "id": sent.id,
                "text": sent.text,
                "section": sent.section,
                "text_ko": sent.text_ko or "",
                "text_ko_stage": sent.text_ko_stage or "",
            },
            "figures": [_fig_public(f) for f in self.figures],
            "sentences": [
                {
                    "id": s.id,
                    "text": s.text,
                    "section": s.section,
                    "text_ko": s.text_ko or "",
                    "text_ko_stage": s.text_ko_stage or "",
                }
                for s in self.sentences
            ],
            "translate_digests": {
                str(k): {
                    "en": str((v or {}).get("en") or ""),
                    "ko": str((v or {}).get("ko") or ""),
                }
                for k, v in (self.translate_digests or {}).items()
                if isinstance(v, dict)
            },
            "references": [
                {
                    "n": int(r["n"]),
                    "text": str(r.get("text") or ""),
                    "doi": str(r.get("doi") or ""),
                }
                for r in (self.references or [])
                if isinstance(r, dict)
                and str(r.get("text") or "").strip()
                and _ref_n_ok(r.get("n"))
            ],
        }


def _ref_n_ok(n: object) -> bool:
    try:
        v = int(n)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return 1 <= v <= 9999


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
        Sentence(id="s-1", text="Ni catalyst was a convenient material for the model reaction.[1]"),
        Sentence(
            id="s-2",
            text="As shown in Figure 1, the active sites remain stable after pretreatment.",
        ),
        Sentence(
            id="s-3",
            text="We then examined the diffraction pattern; see Figure 2 for the main peaks.[2]",
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
    references = [
        {
            "n": 1,
            "text": (
                "B. Liu, J. Sunarso, Y. Zhang, G. Yang, W. Zhou, Z. Shao, "
                "ChemElectroChem 2018, 5, 785."
            ),
            "doi": "",
        },
        {
            "n": 2,
            "text": (
                "Example Author, J. Am. Chem. Soc. 2020, 142, 1-10. "
                "doi:10.1021/jacs.0c00000"
            ),
            "doi": "10.1021/jacs.0c00000",
        },
    ]
    return PaperSession(
        title="Mock paper (skeleton)",
        figures=figures,
        sentences=sentences,
        references=references,
    )
