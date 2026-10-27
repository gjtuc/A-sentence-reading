"""design/472 — cut Noto Sans KR down to the web's Hangul fallback.

Usage: python scripts/make_web_hangul_font.py <NotoSansKR[wght].ttf>
(the variable font from github.com/google/fonts, ofl/notosanskr).

Keeps the 2,350 KS X 1001 syllables, every syllable written in mobile/lib,
jamo and CJK punctuation, at weights 400 and 700.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "mobile" / "assets" / "fonts"
RANGES = [(0x1100, 0x11FF), (0x3130, 0x318F), (0xAC00, 0xD7A3), (0x3000, 0x303F)]


def _ks_x_1001(c: int) -> bool:
    if not 0xAC00 <= c <= 0xD7A3:
        return True
    try:
        return len(chr(c).encode("euc_kr")) == 2
    except UnicodeEncodeError:
        return False


def main(src: str) -> int:
    ui: set[int] = set()
    for p in (ROOT / "mobile" / "lib").rglob("*.dart"):
        text = p.read_text(encoding="utf-8")
        ui.update(ord(c) for c in re.findall(r"[\uac00-\ud7a3]", text))
    keep = {c for a, b in RANGES for c in range(a, b + 1) if _ks_x_1001(c)} | ui
    for weight, name in ((400, "Regular"), (700, "Bold")):
        font = instancer.instantiateVariableFont(TTFont(src), {"wght": weight})
        opts = subset.Options()
        opts.layout_features = ["*"]
        opts.hinting = False
        opts.name_IDs = ["*"]
        opts.notdef_outline = True
        sub = subset.Subsetter(opts)
        sub.populate(unicodes=sorted(keep))
        sub.subset(font)
        out = OUT / f"NotoSansKR-{name}.ttf"
        font.save(str(out))
        print(out.name, out.stat().st_size)
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
