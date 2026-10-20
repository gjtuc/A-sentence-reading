"""Letters the PDF draws without naming them, and the PDF's own sub/superscripts (design/433).

A PDF character has two parts: the shape the font draws and, separately, the Unicode
character it stands for (the ToUnicode map). Some fonts leave the second part out. The
shape still prints correctly, but extraction gets a control code, private-use code or
U+FFFD. `get_text("words")` treats a control code as a space, so `cm−2` reaches the
sentences as `cm 2`.

Measured over 198 papers on this PC: 110 have such characters, 467 distinct shapes in
69 fonts, and 89% of the shapes occur in one paper only, so a hand-kept table would
never stop growing. Each shape is named in this order:

    the font's own glyph name, read as Unicode (Adobe Glyph List)    6% of characters
    one Gemini vision call per sheet of 12 shapes, per paper         38 of 47 labelled
    for dashes, the glyph's own context (minus in a script, en dash between digits)

The layout service reads 13 of the same 47 and flattens symbols to ASCII look-alikes,
so it is not used for this.

Sub/superscripts come from geometry the PDF already has: a glyph smaller than its
line's text whose baseline moves up is a superscript; one that moves down is a
subscript. On the paper that raised this (body 8.0 pt, scripts 5.64 pt, rises −3.56 pt
and drops +1.3 pt) every script in the sentence was recovered.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import threading
import unicodedata
from bisect import bisect_left
from collections import Counter, OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass, field

# pymupdf.TEXTFLAGS_WORDS: the flags `get_text("words")` reads with, so the words built
# here are the words it would build.
WORD_FLAGS = 195

# A script is smaller than this share of its line's text size...
SCRIPT_SIZE = 0.85
# ...and its baseline moves by more than this share of that size. Measured scripts move
# 0.16 (subscript) and 0.44 (superscript) of the body size.
SCRIPT_SHIFT = 0.06
# A size carrying at least this share of a line's glyphs can be the line's text size,
# so a line that wraps right after `cm` still measures `−2` against `cm`.
LINE_SIZE_SHARE = 0.3

VISION_CELLS = 12
# Shapes beyond this many in one paper stay as they are. 467 shapes over 110 papers;
# the largest, a whole text font with no character map, has 85.
VISION_MAX_GLYPHS = 120
VISION_TIMEOUT_S = 60.0

# A plain form takes its PDF markup only when at least this share of the paper's
# occurrences of that form carry the same markup.
FORM_AGREEMENT = 0.8

DASHES = "-\u2010\u2011\u2012\u2013\u2014\u2212"
MINUS = "\u2212"
EN_DASH = "\u2013"

_CACHE_FILES = 8
_BY_FILE: OrderedDict[str, GlyphFixes] = OrderedDict()
_PENDING: dict[str, Future] = {}
_LOCK = threading.Lock()

_VISION_SYSTEM = """You identify single characters in crops of scientific PDF pages.
Each numbered cell shows a little text; one character or ligature is inside a thin red box.
Name exactly what is printed inside the red box as Unicode, telling apart look-alikes:
minus sign U+2212 vs hyphen vs en dash U+2013 vs em dash U+2014; tilde operator U+223C vs ~;
micro sign vs Greek mu; degree sign vs ring; multiplication sign U+00D7 vs letter x;
Greek letters (alpha, gamma, nu, Delta...) vs Latin look-alikes; copyright vs @.
A ligature joins letters into one shape (fi, fl, ff, ffi, ffl): answer all its letters.
If the red box holds no ink, answer a single space.
Answer the character itself, not its code point.
Answer JSON only: {"<cell number>": "<character>", ...}. No commentary."""

_CODE_POINT = re.compile(r"^(?:U\+([0-9A-Fa-f]{4,6})\s*)+$")


def is_unnamed(code: int) -> bool:
    """A code that names no character: control, private use, U+FFFD."""
    if code < 0x20 and code not in (9, 10, 13):
        return True
    return 0xE000 <= code <= 0xF8FF or code == 0xFFFD or code >= 0xF0000


def font_base(name: str) -> str:
    """The font name without its subset prefix (`ABCDEF+AdvP4C4E74`)."""
    return str(name or "").split("+", 1)[-1]


def delimits(c: str) -> bool:
    """MuPDF's word delimiter: any code up to the space, and the no-break space."""
    return len(c) == 1 and (ord(c) <= 32 or ord(c) == 160)


@dataclass(slots=True)
class Glyph:
    c: str
    bbox: tuple[float, float, float, float]
    size: float
    ox: float
    oy: float
    script: str = ""
    key: tuple[str, int] | None = None


@dataclass
class GlyphFixes:
    """What each unnamed shape stands for in one paper, keyed by (font, glyph id)."""

    text: dict[tuple[str, int], str] = field(default_factory=dict)
    census: Counter = field(default_factory=Counter)


@dataclass
class _Seen:
    n: int = 0
    script: int = 0
    between_digits: int = 0
    signs_a_number: int = 0
    page: int = 0
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    size: float = -1.0


def _inked(g: Glyph) -> bool:
    return not delimits(g.c) or (len(g.c) == 1 and is_unnamed(ord(g.c)))


def mark_scripts(row: list[Glyph]) -> None:
    """Mark the glyphs of one line that sit above or below its text.

    A small glyph is measured against the nearest full-size glyph beside it, not
    against the line as a whole: a table row or an inline formula can hold more than
    one baseline.
    """
    weights = Counter(round(g.size, 1) for g in row if _inked(g))
    if not weights:
        return
    total = sum(weights.values())
    ref = max(s for s, n in weights.items() if n >= LINE_SIZE_SHARE * total)
    full = [i for i, g in enumerate(row) if _inked(g) and g.size >= SCRIPT_SIZE * ref]
    if not full:
        return
    for i, g in enumerate(row):
        if not _inked(g) or g.size >= SCRIPT_SIZE * ref:
            continue
        k = bisect_left(full, i)
        nb = row[full[k - 1]] if k else row[full[k]]
        dy = g.oy - nb.oy
        if dy < -SCRIPT_SHIFT * nb.size:
            g.script = "sup"
        elif dy > SCRIPT_SHIFT * nb.size:
            g.script = "sub"


def page_glyph_lines(page) -> list[list[Glyph]]:
    """Every line on the page as glyphs, scripts marked, unnamed glyphs keyed."""
    raw = page.get_text("rawdict", flags=WORD_FLAGS)
    lines: list[list[Glyph]] = []
    unnamed: list[Glyph] = []
    for block in raw.get("blocks") or []:
        for line in block.get("lines") or []:
            row: list[Glyph] = []
            for span in line.get("spans") or []:
                size = float(span.get("size") or 0.0)
                for ch in span.get("chars") or []:
                    c = str(ch.get("c") or "")
                    ox, oy = ch.get("origin") or (0.0, 0.0)
                    g = Glyph(c, tuple(ch.get("bbox") or (0, 0, 0, 0)), size, float(ox), float(oy))
                    if len(c) == 1 and is_unnamed(ord(c)):
                        unnamed.append(g)
                    row.append(g)
            if row:
                mark_scripts(row)
                lines.append(row)
    if unnamed:
        at: dict[tuple[float, float], tuple[str, int]] = {}
        for span in page.get_texttrace() or []:
            base = font_base(span.get("font"))
            for ch in span.get("chars") or ():
                if is_unnamed(int(ch[0])):
                    at[(round(ch[2][0], 1), round(ch[2][1], 1))] = (base, int(ch[1]))
        for g in unnamed:
            g.key = at.get((round(g.ox, 1), round(g.oy, 1)))
    return lines


def _doc_lines(doc, pno: int) -> list[list[Glyph]]:
    cache = getattr(doc, "_asr_glyph_lines", None)
    if cache is None:
        cache = {}
        try:
            doc._asr_glyph_lines = cache
        except Exception:  # noqa: BLE001
            pass
    if pno not in cache:
        cache[pno] = page_glyph_lines(doc[pno])
    return cache[pno]


def glyph_text(g: Glyph, fixes: dict[tuple[str, int], str]) -> str:
    if g.key is not None and g.key in fixes:
        return fixes[g.key]
    return g.c


def words_from_lines(
    lines: list[list[Glyph]], fixes: dict[tuple[str, int], str]
) -> list[tuple[float, float, float, float, str]]:
    """The words `get_text("words")` would return, with unnamed glyphs named."""
    out: list[tuple[float, float, float, float, str]] = []
    for row in lines:
        for word in _row_words(row, fixes):
            x0 = min(g.bbox[0] for g, _ in word)
            y0 = min(g.bbox[1] for g, _ in word)
            x1 = max(g.bbox[2] for g, _ in word)
            y1 = max(g.bbox[3] for g, _ in word)
            out.append((float(x0), float(y0), float(x1), float(y1), "".join(t for _, t in word)))
    return out


def _row_words(
    row: list[Glyph], fixes: dict[tuple[str, int], str]
) -> list[list[tuple[Glyph, str]]]:
    words: list[list[tuple[Glyph, str]]] = []
    cur: list[tuple[Glyph, str]] = []
    for g in row:
        t = glyph_text(g, fixes)
        if not t or delimits(t):
            if cur:
                words.append(cur)
                cur = []
            continue
        cur.append((g, t))
    if cur:
        words.append(cur)
    return words


def page_words_named(page) -> list[tuple[float, float, float, float, str]] | None:
    """The page's words with unnamed glyphs named, or None when nothing needed naming."""
    doc = page.parent
    fixes = doc_glyph_fixes(doc)
    if not fixes.text:
        return None
    return words_from_lines(_doc_lines(doc, page.number), fixes.text)


# ---------------------------------------------------------------------------
# Naming unnamed glyphs, once per paper.


def doc_glyph_fixes(doc, *, vision=None) -> GlyphFixes:
    """Cached on the document and, by content, across reopenings of the same file.

    A run already under way for the same file (see `prefetch`) is waited for rather
    than repeated, so a paper costs one set of vision calls.
    """
    cached = getattr(doc, "_asr_glyph_fixes", None)
    if isinstance(cached, GlyphFixes):
        return cached
    digest = _path_digest(getattr(doc, "name", "") or "")
    fixes = _by_digest(digest, lambda: _resolve(doc, vision))
    try:
        doc._asr_glyph_fixes = fixes
    except Exception:  # noqa: BLE001
        pass
    return fixes


def prefetch(path) -> None:
    """Start naming a file's glyphs in the background, e.g. while the layout service reads it."""
    digest = _path_digest(path)
    if not digest:
        return

    def work() -> None:
        try:
            import pymupdf

            doc = pymupdf.open(str(path))
        except Exception:  # noqa: BLE001
            return
        try:
            _by_digest(digest, lambda: _resolve(doc, None))
        except Exception:  # noqa: BLE001
            pass
        finally:
            doc.close()

    threading.Thread(target=work, name="glyph-prefetch", daemon=True).start()


def _by_digest(digest: str, compute) -> GlyphFixes:
    if not digest:
        return compute()
    with _LOCK:
        fixes = _BY_FILE.get(digest)
        if fixes is not None:
            return fixes
        pending = _PENDING.get(digest)
        owner = pending is None
        if owner:
            pending = _PENDING[digest] = Future()
    if not owner:
        return pending.result()
    try:
        fixes = compute()
    except BaseException as exc:
        with _LOCK:
            _PENDING.pop(digest, None)
        pending.set_exception(exc)
        raise
    with _LOCK:
        _BY_FILE[digest] = fixes
        while len(_BY_FILE) > _CACHE_FILES:
            _BY_FILE.popitem(last=False)
        _PENDING.pop(digest, None)
    pending.set_result(fixes)
    return fixes


def census_for_path(path) -> dict[str, int]:
    """The naming census of a file already read in this process, for the ingest warnings."""
    fixes = _BY_FILE.get(_path_digest(path))
    return dict(fixes.census) if fixes else {}


def _path_digest(path) -> str:
    name = str(path or "")
    if not name or not os.path.isfile(name):
        return ""
    try:
        with open(name, "rb") as fh:
            return hashlib.sha1(fh.read()).hexdigest()
    except OSError:
        return ""


def _resolve(doc, vision) -> GlyphFixes:
    fixes = GlyphFixes()
    seen: dict[tuple[str, int], _Seen] = {}
    for pno in range(doc.page_count):
        for row in _doc_lines(doc, pno):
            for i, g in enumerate(row):
                if g.key is None:
                    continue
                s = seen.setdefault(g.key, _Seen())
                s.n += 1
                prev = row[i - 1].c if i else " "
                nxt = row[i + 1].c if i + 1 < len(row) else " "
                if g.script:
                    s.script += 1
                if prev.isdigit() and nxt.isdigit():
                    s.between_digits += 1
                elif (delimits(prev) or prev in "([") and nxt.isdigit():
                    s.signs_a_number += 1
                if g.size > s.size:
                    s.page, s.bbox, s.size = pno, g.bbox, g.size
    if not seen:
        return fixes
    fixes.census["unnamed_glyphs"] = len(seen)
    fixes.census["unnamed_chars"] = sum(s.n for s in seen.values())

    names = _glyph_names(doc, {k[0] for k in seen})
    for key in seen:
        text = text_from_glyph_name(names.get(key[0], {}).get(key[1], ""))
        if text:
            fixes.text[key] = text
            fixes.census["named_by_font"] += 1

    rest = sorted((k for k in seen if k not in fixes.text), key=lambda k: -seen[k].n)
    rest = rest[:VISION_MAX_GLYPHS]
    if rest:
        answers = _ask_vision(doc, rest, seen, fixes.census, vision)
        for key, text in answers.items():
            fixes.text[key] = dash_by_context(text, seen[key])
            fixes.census["named_by_vision"] += 1
    fixes.census["unresolved"] = len(seen) - len(fixes.text)
    return fixes


def dash_by_context(text: str, seen: _Seen) -> str:
    """A dash's length is hard to see in a crop; where it is used is not."""
    if text not in DASHES or seen.n <= 0:
        return text
    if 2 * seen.script > seen.n or 2 * seen.signs_a_number > seen.n:
        return MINUS
    if 2 * seen.between_digits > seen.n:
        return EN_DASH
    return text


def text_from_glyph_name(name: str) -> str:
    """The character a glyph name spells, or '' (`minus`, `uni2212`, `fi`; not `C121`)."""
    if not name or name == ".notdef":
        return ""
    try:
        from fontTools import agl
    except ImportError:
        return ""
    text = agl.toUnicode(name)
    if not text:
        return ""
    text = "".join(
        unicodedata.normalize("NFKC", c) if 0xFB00 <= ord(c) <= 0xFB06 else c for c in text
    )
    if any(is_unnamed(ord(c)) for c in text):
        return ""
    return text


def _glyph_names(doc, bases: set[str]) -> dict[str, dict[int, str]]:
    """glyph id -> glyph name, from each embedded font program that is wanted."""
    xrefs: dict[str, int] = {}
    for pno in range(doc.page_count):
        try:
            for f in doc[pno].get_fonts(full=True):
                base = font_base(f[3])
                if base in bases and base not in xrefs:
                    xrefs[base] = int(f[0])
        except Exception:  # noqa: BLE001
            continue
        if len(xrefs) == len(bases):
            break
    out: dict[str, dict[int, str]] = {}
    for base, xref in xrefs.items():
        out[base] = _font_glyph_names(doc, xref)
    return out


def _font_glyph_names(doc, xref: int) -> dict[int, str]:
    try:
        _, ext, _, buf = doc.extract_font(xref)
    except Exception:  # noqa: BLE001
        return {}
    if not buf:
        return {}
    try:
        if ext in ("cff", "otf") and buf[:4] != b"OTTO":
            from fontTools.cffLib import CFFFontSet

            cff = CFFFontSet()
            cff.decompile(io.BytesIO(buf), None)
            return dict(enumerate(cff[cff.fontNames[0]].charset))
        if ext in ("ttf", "otf"):
            from fontTools.ttLib import TTFont

            return dict(enumerate(TTFont(io.BytesIO(buf), lazy=True).getGlyphOrder()))
    except Exception:  # noqa: BLE001
        return {}
    return {}


def vision_enabled() -> bool:
    if (os.environ.get("ASR_GLYPH_VISION") or "").strip().lower() in ("0", "false", "off"):
        return False
    try:
        from sentence_reading.llm.env import gemini_api_key

        return bool(gemini_api_key())
    except Exception:  # noqa: BLE001
        return False


def _ask_vision(doc, keys, seen, census, vision) -> dict[tuple[str, int], str]:
    """One call per sheet of up to 12 shapes; the sheets of one paper run together."""
    if vision is None:
        if not vision_enabled():
            census["vision_skipped"] += 1
            return {}
        from sentence_reading.llm.vision_ocr import _call_gemini_vision

        def vision(png: bytes, n: int) -> str:
            cells = ", ".join(str(i + 1) for i in range(n))
            return _call_gemini_vision(
                _VISION_SYSTEM, f"Cells: {cells}", png, timeout_s=VISION_TIMEOUT_S
            )

    batches = [keys[i : i + VISION_CELLS] for i in range(0, len(keys), VISION_CELLS)]

    def run(batch):
        png = sheet_png(doc, [seen[k] for k in batch])
        return batch, parse_vision_answer(vision(png, len(batch)), len(batch))

    out: dict[tuple[str, int], str] = {}
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=max(1, len(batches))) as pool:
        futures = [pool.submit(run, b) for b in batches]
        for fut in futures:
            census["vision_calls"] += 1
            try:
                batch, answers = fut.result()
            except Exception:  # noqa: BLE001
                census["vision_failed"] += 1
                continue
            for i, key in enumerate(batch):
                text = answers.get(i + 1, "")
                if text:
                    out[key] = text
    return out


def parse_vision_answer(raw: str, n: int) -> dict[int, str]:
    """`{"1": "−", ...}` -> {1: "−"}; anything that is not a short real string is dropped."""
    m = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return {}
    out: dict[int, str] = {}
    for k, v in (data or {}).items():
        try:
            i = int(str(k).strip())
        except ValueError:
            continue
        if not (1 <= i <= n) or not isinstance(v, str):
            continue
        if v.isspace() and v:
            out[i] = " "
            continue
        v = v.strip()
        if _CODE_POINT.match(v):
            v = "".join(chr(int(h, 16)) for h in re.findall(r"U\+([0-9A-Fa-f]{4,6})", v))
        if not v or len(v) > 3 or any(is_unnamed(ord(c)) for c in v):
            continue
        out[i] = v
    return out


def _cell(doc, s: _Seen):
    from PIL import Image, ImageDraw

    page = doc[s.page]
    x0, y0, x1, y1 = s.bbox
    h = max(y1 - y0, s.size, 6.0)
    import pymupdf

    ctx = pymupdf.Rect(x0 - 5 * h, y0 - 0.8 * h, x1 + 5 * h, y1 + 0.8 * h) & page.rect
    z = 90 / max(ctx.height, 1)
    pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), clip=ctx)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    ImageDraw.Draw(img).rectangle(
        [
            (x0 - ctx.x0) * z - 2,
            (y0 - ctx.y0) * z - 2,
            (x1 - ctx.x0) * z + 2,
            (y1 - ctx.y0) * z + 2,
        ],
        outline=(255, 0, 0),
        width=2,
    )
    img.thumbnail((620, 100))
    return img


def sheet_png(doc, samples: list[_Seen]) -> bytes:
    """Numbered rows, one crop per shape, the shape in a red box."""
    from PIL import Image, ImageDraw, ImageFont

    w, h = 700, 112
    out = Image.new("RGB", (w, h * len(samples)), "white")
    draw = ImageDraw.Draw(out)
    try:
        font = ImageFont.load_default(size=22)
    except TypeError:
        font = ImageFont.load_default()
    for k, s in enumerate(samples):
        draw.text((6, k * h + 40), str(k + 1), fill=(0, 0, 200), font=font)
        out.paste(_cell(doc, s), (70, k * h + 6))
    buf = io.BytesIO()
    out.save(buf, "PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# The PDF's own sub/superscripts, as plain form -> marked form.

_LEAD = "([{\"'\u201c\u2018"
_TRAIL = ")]}.,;:!?\"'\u201d\u2019"


def form_key(plain: str) -> str:
    """The same word however the dashes and the micro sign were written."""
    out = []
    for c in plain:
        if c in DASHES:
            out.append("-")
        elif c == "\u03bc":
            out.append("\u00b5")
        elif c in "\u200b\u200c\u200d\u00ad":
            continue
        else:
            out.append(c)
    return "".join(out)


def _strip_word(word: list[tuple[Glyph, str]]) -> list[tuple[Glyph, str]]:
    a, b = 0, len(word)
    while a < b and not word[a][0].script and word[a][1] in _LEAD:
        a += 1
    while b > a and not word[b - 1][0].script and word[b - 1][1] in _TRAIL:
        b -= 1
    return word[a:b]


_DEGREE_LOOKALIKE = ("o", "0", "\u00ba", "\u02da", "\u00b0")


def _marked(word: list[tuple[Glyph, str]]) -> str:
    out: list[str] = []
    open_tag = ""
    for i, (g, t) in enumerate(word):
        # A raised `o` before C or F is how some papers print the degree sign.
        if (
            g.script == "sup"
            and t in _DEGREE_LOOKALIKE
            and (i == 0 or word[i - 1][0].script != "sup")
            and i + 1 < len(word)
            and not word[i + 1][0].script
            and word[i + 1][1] in ("C", "F")
        ):
            if open_tag:
                out.append(f"</{open_tag}>")
                open_tag = ""
            out.append("\u00b0")
            continue
        if g.script != open_tag:
            if open_tag:
                out.append(f"</{open_tag}>")
            if g.script:
                out.append(f"<{g.script}>")
            open_tag = g.script
        out.append(t)
    if open_tag:
        out.append(f"</{open_tag}>")
    return "".join(out)


def script_forms(doc) -> dict[str, str]:
    """Words the PDF prints with scripts, keyed by `form_key` of their plain letters.

    A form is kept only when the word also has letters on the line (a lone superscript
    `12` would otherwise mark every `12`), and when the paper prints it that way at
    least `FORM_AGREEMENT` of the time.
    """
    fixes = doc_glyph_fixes(doc).text
    # Votes are on where the markup sits, so `cm<sup>−2</sup>` and `cm<sup>-2</sup>`
    # agree; the spelling kept is the one printed most often.
    votes: dict[str, Counter] = {}
    spellings: dict[str, Counter] = {}
    for pno in range(doc.page_count):
        for row in _doc_lines(doc, pno):
            for word in _row_words(row, fixes):
                core = _strip_word(word)
                if not core:
                    continue
                plain = "".join(t for _, t in core)
                if any(c in plain for c in "<>&"):
                    continue
                scripted = any(g.script for g, _ in core)
                if scripted and all(g.script for g, _ in core):
                    continue
                key = form_key(plain)
                marked = _marked(core) if scripted else ""
                votes.setdefault(key, Counter())[form_key(marked)] += 1
                if marked:
                    spellings.setdefault(key, Counter())[marked] += 1
    forms: dict[str, str] = {}
    for key, counts in votes.items():
        shape, n = counts.most_common(1)[0]
        if shape and n >= FORM_AGREEMENT * sum(counts.values()):
            forms[key] = next(
                m for m, _ in spellings[key].most_common() if form_key(m) == shape
            )
    return forms


_TAG = re.compile(r"</?(sub|sup|i|em)>")
_SPACES = re.compile(r"(\s+)")


def _balanced(html: str) -> bool:
    stack: list[str] = []
    for m in _TAG.finditer(html):
        tag = m.group(1)
        if m.group(0).startswith("</"):
            if not stack or stack.pop() != tag:
                return False
        else:
            stack.append(tag)
    return not stack


def apply_script_forms(text: str, forms: dict[str, str]) -> tuple[str, int]:
    """Give each word of a sentence the PDF's own markup. Italic words are left alone."""
    if not text or not forms:
        return text, 0
    parts = _SPACES.split(text)
    changed = 0
    for i in range(0, len(parts), 2):
        tok = parts[i]
        if not tok or "i>" in tok or "em>" in tok:
            continue
        a, b = 0, len(tok)
        while a < b and tok[a] in _LEAD:
            a += 1
        while b > a and tok[b - 1] in _TRAIL:
            b -= 1
        core = tok[a:b]
        if not core or not _balanced(core):
            continue
        plain = _TAG.sub("", core)
        if "<" in plain or ">" in plain:
            continue
        marked = forms.get(form_key(plain))
        if marked and marked != core:
            parts[i] = tok[:a] + marked + tok[b:]
            changed += 1
    return "".join(parts), changed


def script_forms_for_path(path) -> dict[str, str]:
    """`script_forms` of a PDF file; {} when it cannot be read."""
    try:
        import pymupdf

        doc = pymupdf.open(str(path))
    except Exception:  # noqa: BLE001
        return {}
    try:
        return script_forms(doc)
    except Exception:  # noqa: BLE001
        return {}
    finally:
        doc.close()
