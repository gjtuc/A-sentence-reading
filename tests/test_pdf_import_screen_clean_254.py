# Contract test for design 254
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCREEN = ROOT / "mobile" / "lib" / "screens" / "pdf_import_screen.dart"
DESIGN = ROOT / "docs" / "design" / "254-import-screen-tab-cta-separation.md"


def test_design_254_doc_exists():
    assert DESIGN.is_file()
    text = DESIGN.read_text(encoding="utf-8")
    assert "0.3.247" in text
    assert "\ub2e4\uc6b4\ub85c\ub4dc\uc5d0\uc11c \uac00\uc838\uc624\uae30" in text
    assert "\ub17c\ubb38 \ud3f4\ub354 \uc5f0\uac10"[:5] in text
    assert "\ub610\ub294 \ud30c\uc77c\uc5d0\uc11c \ucd94\uac00" in text


def test_pdf_import_screen_cta_separation():
    code = SCREEN.read_text(encoding="utf-8")
    assert "isDownloads: browseDownloads" in code
    assert "final bool isDownloads;" in code
    empty_block = code[code.find("class _EmptyConnect"):]
    assert "if (isDownloads)" in empty_block
    assert "\ub2e4\uc6b4\ub85c\ub4dc \ud3f4\ub354\uc5d0 \uc788\ub294" in empty_block

    bottom_idx = code.find("if (grant != null)")
    assert bottom_idx != -1
    empty_idx = code.find("class _EmptyConnect")
    bottom_bar_part = code[bottom_idx:empty_idx]
    assert "\ub2e4\uc6b4\ub85c\ub4dc\uc5d0\uc11c \uac00\uc838\uc624\uae30" not in bottom_bar_part
    assert "\ud30c\uc77c\uc5d0\uc11c \ucd94\uac00" in bottom_bar_part
    assert "\ub300\uae30\uc5f4\uc5d0 \ucd94\uac00" in bottom_bar_part
    assert "\ub17c\ubb38 \ud3f4\ub354\ub85c \uac00\uc838\uc624\uae30" in bottom_bar_part

