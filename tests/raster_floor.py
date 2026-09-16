"""Synthetic PNGs for extract tests.

docx extract drops blobs under ``_MIN_BYTES``. A solid 40×40 PNG compresses
under that floor, so tests must not pick a pixel size and hope.
"""

from __future__ import annotations

import random
from io import BytesIO

from PIL import Image

from sentence_reading.docx.extract import _MIN_BYTES


def png_over_docx_min() -> bytes:
    """Return a PNG whose byte size is at least the docx extract floor."""
    side = 48
    seed = 1
    while side <= 256:
        blob = _noise_png(side, seed)
        if len(blob) >= _MIN_BYTES:
            return blob
        side += 16
        seed += 1
    raise RuntimeError(f"png never reached docx floor {_MIN_BYTES}")


def _noise_png(side: int, seed: int) -> bytes:
    rnd = random.Random(seed)
    im = Image.new("RGB", (side, side))
    im.putdata(
        [
            (rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
            for _ in range(side * side)
        ]
    )
    buf = BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()
