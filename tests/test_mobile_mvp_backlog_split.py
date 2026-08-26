"""design/140 — Flutter MVP backlog split (docs only)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D140 = ROOT / "docs" / "design" / "140-mobile-mvp-backlog-split.md"
D141 = ROOT / "docs" / "design" / "141-mobile-sentence-notes.md"
D142 = ROOT / "docs" / "design" / "142-no-keyboard-sentence-notes.md"
D33 = ROOT / "docs" / "design" / "33-mobile-flutter.md"
MILES = ROOT / "docs" / "design" / "00-milestones.md"
README = ROOT / "docs" / "design" / "README.md"


def test_split_docs_exist_and_lock_next() -> None:
    assert D140.is_file()
    t140 = D140.read_text(encoding="utf-8")
    assert "141" in t140
    assert "기능 코딩" in t140 or "코드 구현하지" in t140
    # WHY: deleted candidates must not re-enter the split list as active work.
    assert "DOCX" in t140 and "삭제" in t140
    assert "APK 자체 업데이트" in t140
    assert "맨 마지막" in t140 or "맨 뒤" in t140
    assert "142" in t140
    assert "재분석" in t140
    assert "146a" in t140
    assert "146c" in t140 or "카카오" in t140
    assert "계정 연결" in t140 or "계정 연결/해제" in t140

    assert D141.is_file()
    t141 = D141.read_text(encoding="utf-8")
    assert "CANCELLED" in t141
    assert "하지 않음" in t141

    assert D142.is_file()
    # Historical chip pin stays 0.3.58.
    assert "0.3.58" in D142.read_text(encoding="utf-8")


def test_33_and_milestones_point_to_split() -> None:
    t33 = D33.read_text(encoding="utf-8")
    assert "140-mobile-mvp-backlog-split" in t33
    assert "141-mobile-sentence-notes" in t33
    assert "142-no-keyboard-sentence-notes" in t33
    # Stale open checkbox closed.
    assert "- [ ] APK를 실기에 설치해 Cloud Run에 로그인 확인" not in t33
    assert "- [x] APK를 실기에 설치해 Cloud Run에 로그인 확인" in t33

    miles = MILES.read_text(encoding="utf-8")
    assert "140-mobile-mvp-backlog-split" in miles
    assert "141-mobile-sentence-notes" in miles
    assert "142-no-keyboard-sentence-notes" in miles
    # Old open mega-bullet gone.
    assert "**Android Flutter MVP** — 남은 실기 완성도" not in miles
    assert "모바일 문장 노트" not in miles.split("**다음 구현:**")[-1][:80]

    readme = README.read_text(encoding="utf-8")
    assert "140-mobile-mvp-backlog-split" in readme
    assert "141-mobile-sentence-notes" in readme
    assert "142-no-keyboard-sentence-notes" in readme
