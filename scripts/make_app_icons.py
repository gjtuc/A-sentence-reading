"""Draw the app mark (cream page, blue sentence bar) at any size.

Geometry is the Android launcher icon (mipmap-xxxhdpi, 192 px), so the web,
the installed PC app and the phone show the same mark.

    python scripts/make_app_icons.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "mobile" / "web"

BG = (18, 18, 18)
PAGE = (244, 241, 234)
FOLD = (205, 197, 182)
BAR = (42, 42, 42)
BLUE = (92, 160, 212)
INNER = (255, 255, 255)
SUPER = 4


def draw(size: int) -> Image.Image:
    big = size * SUPER
    k = big / 192.0

    def r(*v: float) -> list[float]:
        return [c * k for c in v]

    im = Image.new("RGB", (big, big), BG)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle(r(41, 30, 151, 162), radius=6 * k, fill=PAGE)
    d.polygon([tuple(r(128, 30)), tuple(r(151, 30)), tuple(r(151, 53))], fill=FOLD)
    d.rounded_rectangle(r(57, 57, 136, 64), radius=2 * k, fill=BAR)
    d.rounded_rectangle(r(52, 74, 140, 92), radius=4 * k, fill=BLUE)
    d.rounded_rectangle(r(57, 79, 135, 87), radius=1 * k, fill=INNER)
    d.rounded_rectangle(r(57, 102, 115, 109), radius=2 * k, fill=BAR)
    return im.resize((size, size), Image.LANCZOS)


def main() -> None:
    icons = WEB / "icons"
    for size in (192, 512):
        mark = draw(size)
        mark.save(icons / f"Icon-{size}.png", optimize=True)
        # The page sits inside the maskable safe circle, so the same art fits.
        mark.save(icons / f"Icon-maskable-{size}.png", optimize=True)
    draw(32).save(WEB / "favicon.png", optimize=True)
    draw(256).save(
        ROOT / "scripts" / "app_icon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )


if __name__ == "__main__":
    main()
