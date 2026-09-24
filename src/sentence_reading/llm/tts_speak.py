"""
무엇을: TTS에 넘기기 전 말할 말로 정규화 (첨자·기호·구역 접두·단위).
왜: plain_text 만 쓰면 H2O·cm−1·Title: 을 글자 그대로 읽어 어색하다.
다음에: design/205 약어·화학식 별칭·캐시 norm version.
"""

from __future__ import annotations

import html as html_lib
import re
from html.parser import HTMLParser

from sentence_reading.cite_refs import strip_cite_markers_for_display
from sentence_reading.llm.tts_speak_lexicon import (
    ACRONYM_NAME_HINTS,
    ACRONYM_SPOKEN,
    CHEM_ALIASES,
    FORMULA_FRAGMENTS,
)
from sentence_reading.llm.speak_tokens import (
    freeze,
    protect_variable_exponents,
    resolve_variable_exponents,
    restore,
    restore_sentence_case,
    spoken_post,
    voice_definitions,
)
from sentence_reading.llm.tts_speak_policy import SpeakPolicy, load_speak_policy

_SECTION_PREFIX = re.compile(
    r"^\s*(Title|Abstract|Introduction|Methods|Experimental|Results|"
    r"Discussion|Conclusion|Body)\s*:\s*",
    re.IGNORECASE,
)

_DIGIT_WORD = {
    "0": "zero",
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
}

# 원소 기호 → 영어 이름 (TTS). 긴 기호 우선 치환.
_ELEMENT_SPOKEN: dict[str, str] = {
    "Ac": "actinium",
    "Ag": "silver",
    "Al": "aluminum",
    "Am": "americium",
    "Ar": "argon",
    "As": "arsenic",
    "At": "astatine",
    "Au": "gold",
    "B": "boron",
    "Ba": "barium",
    "Be": "beryllium",
    "Bh": "bohrium",
    "Bi": "bismuth",
    "Bk": "berkelium",
    "Br": "bromine",
    "C": "carbon",
    "Ca": "calcium",
    "Cd": "cadmium",
    "Ce": "cerium",
    "Cf": "californium",
    "Cl": "chlorine",
    "Cm": "curium",
    "Cn": "copernicium",
    "Co": "cobalt",
    "Cr": "chromium",
    "Cs": "cesium",
    "Cu": "copper",
    "Db": "dubnium",
    "Ds": "darmstadtium",
    "Dy": "dysprosium",
    "Er": "erbium",
    "Es": "einsteinium",
    "Eu": "europium",
    "F": "fluorine",
    "Fe": "iron",
    "Fl": "flerovium",
    "Fm": "fermium",
    "Fr": "francium",
    "Ga": "gallium",
    "Gd": "gadolinium",
    "Ge": "germanium",
    "H": "hydrogen",
    "He": "helium",
    "Hf": "hafnium",
    "Hg": "mercury",
    "Ho": "holmium",
    "Hs": "hassium",
    "I": "iodine",
    "In": "indium",
    "Ir": "iridium",
    "K": "potassium",
    "Kr": "krypton",
    "La": "lanthanum",
    "Li": "lithium",
    "Lr": "lawrencium",
    "Lu": "lutetium",
    "Lv": "livermorium",
    "Mc": "moscovium",
    "Md": "mendelevium",
    "Mg": "magnesium",
    "Mn": "manganese",
    "Mo": "molybdenum",
    "Mt": "meitnerium",
    "N": "nitrogen",
    "Na": "sodium",
    "Nb": "niobium",
    "Nd": "neodymium",
    "Ne": "neon",
    "Nh": "nihonium",
    "Ni": "nickel",
    "No": "nobelium",
    "Np": "neptunium",
    "O": "oxygen",
    "Og": "oganesson",
    "Os": "osmium",
    "P": "phosphorus",
    "Pa": "protactinium",
    "Pb": "lead",
    "Pd": "palladium",
    "Pm": "promethium",
    "Po": "polonium",
    "Pr": "praseodymium",
    "Pt": "platinum",
    "Pu": "plutonium",
    "Ra": "radium",
    "Rb": "rubidium",
    "Re": "rhenium",
    "Rf": "rutherfordium",
    "Rg": "roentgenium",
    "Rh": "rhodium",
    "Rn": "radon",
    "Ru": "ruthenium",
    "S": "sulfur",
    "Sb": "antimony",
    "Sc": "scandium",
    "Se": "selenium",
    "Sg": "seaborgium",
    "Si": "silicon",
    "Sm": "samarium",
    "Sn": "tin",
    "Sr": "strontium",
    "Ta": "tantalum",
    "Tb": "terbium",
    "Tc": "technetium",
    "Te": "tellurium",
    "Th": "thorium",
    "Ti": "titanium",
    "Tl": "thallium",
    "Tm": "thulium",
    "Ts": "tennessine",
    "U": "uranium",
    "V": "vanadium",
    "W": "tungsten",
    "Xe": "xenon",
    "Y": "yttrium",
    "Yb": "ytterbium",
    "Zn": "zinc",
    "Zr": "zirconium",
}

# 영어 단어와 겹치는 기호 — 단독은 유지, 화학식(숫자·다음 원소)일 때만 이름
_ELEMENT_BARE_SKIP = frozenset({"He", "As", "At", "Be", "In", "No", "I"})

# design/339 — words that make a preceding lone capital an element rather than a
# variable: `N-doped`, `S-containing`, `O-rich`.
_ELEMENT_CONTEXT_WORD = (
    r"(?:doped|doping|containing|rich|poor|based|free|substituted|terminated|"
    r"modified|functionali[sz]ed|deficient|bearing|linked|bridged|coordinated|"
    r"vacanc\w+|atoms?|anions?|cations?|species)"
)

_ELEMENT_KEYS_LONGEST = tuple(
    sorted(_ELEMENT_SPOKEN.keys(), key=len, reverse=True)
)

# 표시용 기호 → 영어 발음 (논문 빈도 높은 것만)
# design/339 — subscripts that are abbreviated words. Everything not listed and
# still a pronounceable lowercase run is spoken as itself rather than spelled.
_SUBSCRIPT_WORD = {
    "obs": "observed",
    "max": "maximum",
    "min": "minimum",
    "avg": "average",
    "eff": "effective",
    "exp": "experimental",
    "calc": "calculated",
    "cal": "calculated",
    "theo": "theoretical",
    "ads": "adsorption",
    "des": "desorption",
    "red": "reduced",
    "ox": "oxidized",
    "tot": "total",
    "sat": "saturation",
    "surf": "surface",
    "app": "apparent",
    "sol": "solution",
    "cat": "catalyst",
    "ref": "reference",
    "std": "standard",
}
_VOWEL_RE = re.compile(r"[aeiouy]")

# design/339 — a letter the printed paper set in italics, or a supplementary label
# letter, wrapped so the element rules cannot rename it. Converted to a frozen
# placeholder right after `freeze`, and restored with everything else.
VAR_MARK = "\x02"
# design/343 — a paper term matched on the printed form, before the HTML parse turns
# its subscripts into words.
_TERM_MARK = "\x03"
_TERM_MARKED = re.compile(r"\x03(\d+)\x03")
_VAR_MARKED = re.compile(r"\x02([A-Za-z])\x02")
# `Fig. S1`, `Table S3`, `Eq. S2` — the S is "supplementary", never sulfur.
_SUPP_LABEL = re.compile(
    r"\b(Fig|Figs|Figure|Figures|Table|Tables|Scheme|Schemes|Eq|Eqs|Equation|"
    r"Section|Note|Notes|Movie|Video|Text|Appendix)(\.?\s+)S(?=\d)"
)
_SUPP_CONTEXT = re.compile(r"supplementary|supporting information", re.IGNORECASE)
_SUPP_BARE = re.compile(r"(?<![A-Za-z\u2019'])S(\d{1,2})\b")

_SYMBOL_SPOKEN = (
    ("≤", " less than or equal to "),
    ("≥", " greater than or equal to "),
    ("≠", " not equal to "),
    ("±", " plus or minus "),
    ("×", " times "),
    ("·", " times "),
    ("→", " goes to "),
    ("⟶", " goes to "),
    ("⇒", " goes to "),
    ("↔", " exchange "),
    ("⇌", " equilibrium "),
    ("∞", " infinity "),
    ("°C", " degrees Celsius "),
    ("°F", " degrees Fahrenheit "),
    ("Å", " angstrom "),
    ("µ", " micro "),
    ("μ", " mu "),
    ("α", " alpha "),
    ("β", " beta "),
    ("γ", " gamma "),
    ("δ", " delta "),
    ("Δ", " delta "),
    ("ε", " epsilon "),
    ("θ", " theta "),
    ("λ", " lambda "),
    ("π", " pi "),
    ("σ", " sigma "),
    ("τ", " tau "),
    ("φ", " phi "),
    ("ω", " omega "),
    ("Ω", " ohm "),
    ("−", " minus "),
    ("–", " "),
    ("—", " "),
    # design/339 — `&gt;` unescapes to a bare `>` and reached TTS as a glyph. All
    # markup is already parsed away by the time this runs, so a surviving angle
    # bracket is a comparison the reader has to hear.
    (">", " greater than "),
    ("<", " less than "),
)

# design/88+90 — 단위 역수 꼬리 (HTML 풀어쓴 뒤 · 유니코드 · 평문)
_INV = (
    r"(?:\s*(?:to\s+the\s+minus\s+one|[⁻−\-]1|⁻¹|\^\s*\{?\s*[−\-]1\s*\}?))"
)
_INV2 = (
    r"(?:\s*(?:to\s+the\s+minus\s+two|[⁻−\-]2|⁻²|\^\s*\{?\s*[−\-]2\s*\}?))"
)
_SLASH_L = r"(?:\s*/\s*L|\s+per\s+L)"
_SLASH_KG = r"(?:\s*/\s*kg|\s+per\s+kg)"
_SLASH_G = r"(?:\s*/\s*g|\s+per\s+g)"
_SLASH_MOL = r"(?:\s*/\s*mol|\s+per\s+mol)"

# 긴 복합 단위 우선 (W≠텅스텐 충돌 전에 처리). design/90.
_UNIT_SPOKEN_RES: tuple[tuple[re.Pattern[str], str], ...] = (
    # design/339 — molar concentrations. `0.4 mM` reached TTS as "zero point four
    # m M", the most common surviving unit defect in the ten-paper corpus.
    (re.compile(r"(?<=\d)\s*mM(?![A-Za-z])"), " millimolar "),
    (re.compile(r"(?<=\d)\s*[µμu]M(?![A-Za-z])"), " micromolar "),
    (re.compile(r"(?<=\d)\s*nM(?![A-Za-z])"), " nanomolar "),
    (re.compile(r"(?<=\d)\s*pM(?![A-Za-z])"), " picomolar "),
    # `35 sec` — the abbreviation was left for TTS to guess.
    (re.compile(r"(?<=\d)\s*sec(?![A-Za-z])"), " seconds "),
    (re.compile(r"(?<=\d)\s*ppm(?![A-Za-z])"), " parts per million "),
    (re.compile(r"(?<=\d)\s*ppb(?![A-Za-z])"), " parts per billion "),
    # --- energy / electricity density ---
    (
        re.compile(
            rf"\bW\s*h\s*L{_INV}\b|\bW\s*h{_SLASH_L}\b|\bWh\s*L{_INV}\b|\bWh{_SLASH_L}\b",
            re.IGNORECASE,
        ),
        " watt hour per liter ",
    ),
    (
        re.compile(
            rf"\bW\s*h\s*kg{_INV}\b|\bW\s*h{_SLASH_KG}\b|\bWh\s*kg{_INV}\b|\bWh{_SLASH_KG}\b",
            re.IGNORECASE,
        ),
        " watt hour per kilogram ",
    ),
    (
        re.compile(
            rf"\bW\s*h\s*g{_INV}\b|\bW\s*h{_SLASH_G}\b|\bWh\s*g{_INV}\b|\bWh{_SLASH_G}\b",
            re.IGNORECASE,
        ),
        " watt hour per gram ",
    ),
    (re.compile(r"\bkW\s*h\b|\bkWh\b", re.IGNORECASE), " kilowatt hour "),
    (re.compile(r"\bMW\s*h\b|\bMWh\b", re.IGNORECASE), " megawatt hour "),
    (re.compile(r"\bW\s*h\b|\bWh\b", re.IGNORECASE), " watt hour "),
    (
        re.compile(
            rf"\bmA\s*h\s*g{_INV}\b|\bmA\s*h{_SLASH_G}\b|\bmAh\s*g{_INV}\b|\bmAh{_SLASH_G}\b",
            re.IGNORECASE,
        ),
        " milliampere hour per gram ",
    ),
    (
        re.compile(
            rf"\bA\s*h\s*g{_INV}\b|\bA\s*h{_SLASH_G}\b|\bAh\s*g{_INV}\b|\bAh{_SLASH_G}\b",
            re.IGNORECASE,
        ),
        " ampere hour per gram ",
    ),
    (re.compile(r"\bmA\s*h\b|\bmAh\b", re.IGNORECASE), " milliampere hour "),
    (re.compile(r"\bA\s*h\b|\bAh\b", re.IGNORECASE), " ampere hour "),
    (
        re.compile(
            rf"\bmA\s*(?:/\s*)?cm{_INV2}\b|\bmA\s*/\s*cm\s*(?:\^?\s*2|²)\b",
            re.IGNORECASE,
        ),
        " milliampere per square centimeter ",
    ),
    # --- thermo / chem ---
    (
        re.compile(rf"\bkJ\s*mol{_INV}\b|\bkJ{_SLASH_MOL}\b", re.IGNORECASE),
        " kilojoule per mole ",
    ),
    (
        re.compile(rf"\bJ\s*mol{_INV}\b|\bJ{_SLASH_MOL}\b", re.IGNORECASE),
        " joule per mole ",
    ),
    (
        re.compile(rf"\bkJ\s*kg{_INV}\b|\bkJ{_SLASH_KG}\b", re.IGNORECASE),
        " kilojoule per kilogram ",
    ),
    (re.compile(r"\beV\b"), " electron volt "),
    (
        re.compile(
            rf"\bmol\s*L{_INV}\b|\bmol{_SLASH_L}\b|\bmol\s*/\s*dm\s*(?:to\s+the\s+three|[⁻−\-]3|⁻³|\^3)\b",
            re.IGNORECASE,
        ),
        " mole per liter ",
    ),
    # --- mass / volume concentration ---
    (
        re.compile(
            rf"\bmg\s*mL{_INV}\b|\bmg\s*/\s*mL\b|\bmg\s+per\s+mL\b",
            re.IGNORECASE,
        ),
        " milligram per milliliter ",
    ),
    (
        re.compile(rf"\bg\s*L{_INV}\b|\bg{_SLASH_L}\b", re.IGNORECASE),
        " gram per liter ",
    ),
    (
        re.compile(rf"\bmg\s*L{_INV}\b|\bmg{_SLASH_L}\b", re.IGNORECASE),
        " milligram per liter ",
    ),
    (
        re.compile(
            rf"\bµg\s*mL{_INV}\b|\bug\s*mL{_INV}\b|\bµg\s*/\s*mL\b|\bug\s*/\s*mL\b",
            re.IGNORECASE,
        ),
        " microgram per milliliter ",
    ),
    # --- spectroscopy / rates ---
    (
        re.compile(
            rf"\bcm{_INV}\b|\bcm\s*\^\s*\{{\s*[−\-]1\s*\}}",
            re.IGNORECASE,
        ),
        " per centimeter ",
    ),
    (re.compile(rf"\bs{_INV}\b", re.IGNORECASE), " per second "),
    (re.compile(r"\bHz\b"), " hertz "),
    (re.compile(r"\brpm\b", re.IGNORECASE), " revolutions per minute "),
    (
        re.compile(r"\bsccm\b", re.IGNORECASE),
        " standard cubic centimeters per minute ",
    ),
    # --- length / area / volume ---
    (
        re.compile(
            r"\bcm\s*(?:to\s+the\s+(?:minus\s+)?two|[⁻−\-]2|⁻²|\^\s*2)\b",
            re.IGNORECASE,
        ),
        " square centimeter ",
    ),
    (
        re.compile(
            r"\bm\s*(?:to\s+the\s+(?:minus\s+)?two|[⁻−\-]2|⁻²|\^\s*2)\b",
            re.IGNORECASE,
        ),
        " square meter ",
    ),
    (
        re.compile(
            r"\bm\s*(?:to\s+the\s+(?:minus\s+)?three|[⁻−\-]3|⁻³|\^\s*3)\b",
            re.IGNORECASE,
        ),
        " cubic meter ",
    ),
    (re.compile(rf"\bm{_INV}\b", re.IGNORECASE), " per meter "),
    (re.compile(rf"\bL{_INV}\b", re.IGNORECASE), " per liter "),
    (re.compile(rf"\bkg{_INV}\b", re.IGNORECASE), " per kilogram "),
    (re.compile(rf"\bg{_INV}\b", re.IGNORECASE), " per gram "),
    # --- pressure / temp / misc ---
    (re.compile(r"\bMPa\b"), " megapascal "),
    (re.compile(r"\bkPa\b"), " kilopascal "),
    (re.compile(r"\bPa\b"), " pascal "),
    (re.compile(r"\batm\b", re.IGNORECASE), " atmosphere "),
    (re.compile(r"\bbar\b", re.IGNORECASE), " bar "),
    (re.compile(r"(?<=\d)\s*K\b"), " kelvin "),
    (re.compile(r"\bwt\.?\s*%", re.IGNORECASE), " weight percent "),
    (re.compile(r"\bmol\s*%", re.IGNORECASE), " mole percent "),
    (re.compile(r"\bppm\b", re.IGNORECASE), " parts per million "),
    (re.compile(r"\bppb\b", re.IGNORECASE), " parts per billion "),
    # --- bare SI after a digit (unit context; avoids tungsten/vanadium…) ---
    (re.compile(r"(?<=\d)\s*kW\b"), " kilowatt "),
    (re.compile(r"(?<=\d)\s*MW\b"), " megawatt "),
    (re.compile(r"(?<=\d)\s*mW\b"), " milliwatt "),
    (re.compile(r"(?<=\d)\s*W\b"), " watt "),
    (re.compile(r"(?<=\d)\s*mV\b"), " millivolt "),
    (re.compile(r"(?<=\d)\s*V\b"), " volt "),
    (re.compile(r"(?<=\d)\s*mA\b"), " milliampere "),
    (re.compile(r"(?<=\d)\s*A\b"), " ampere "),
    (re.compile(r"(?<=\d)\s*(?:Ω|ohm)\b", re.IGNORECASE), " ohm "),
    # scientific 10^n leftover phrasing
    (
        re.compile(r"\b10\s+to\s+the\s+minus\s+", re.IGNORECASE),
        " ten to the minus ",
    ),
)

_LITERAL_TAG_RE = re.compile(
    r"</?\s*(?:sub|sup|i|em)\s*>", re.IGNORECASE
)


def _speak_numberish(raw: str) -> str:
    """첨자/윗첨자 내용 → 짧게 말할 말."""
    s = (raw or "").strip()
    if not s:
        return ""
    s = (
        s.replace("−", "-")
        .replace("–", "-")
        .replace("—", "-")
        .replace("＋", "+")
    )
    # 순수 부호+숫자(+소수)
    m = re.fullmatch(r"([+\-]?)(\d+)(?:\.(\d+))?", s)
    if m:
        sign, whole, frac = m.group(1), m.group(2), m.group(3)
        parts: list[str] = []
        if sign == "-":
            parts.append("minus")
        elif sign == "+":
            parts.append("plus")
        if len(whole) == 1:
            parts.append(_DIGIT_WORD.get(whole, whole))
        elif whole == "10":
            parts.append("ten")
        else:
            parts.extend(_DIGIT_WORD.get(ch, ch) for ch in whole)
        if frac is not None:
            parts.append("point")
            parts.extend(_DIGIT_WORD.get(ch, ch) for ch in frac)
        return " ".join(parts)
    # design/339 — a subscript that is a word is read as a word. Spelling it was
    # the single biggest speech defect: `K obs` became "potassium o b s" and
    # `t ion` became "t i o n", which destroys the sentence's rhythm.
    low = s.lower()
    if low in _SUBSCRIPT_WORD:
        return _SUBSCRIPT_WORD[low]
    if len(s) >= 2 and s.islower() and _VOWEL_RE.search(low):
        return low
    # 짧은 원소/기호: 글자 사이 공백. Orbital labels (`g`, `2g`) belong here.
    if re.fullmatch(r"[A-Za-z]{1,4}", s):
        return " ".join(s)
    # design/339 — the old guard excluded any non-ASCII character, so `O<sub>3-δ</sub>`
    # fell through untouched and reached TTS as "oxygen 3- delta". Greek letters
    # belong in a subscript; digits and signs still get spoken.
    if len(s) <= 8:
        out: list[str] = []
        for ch in s:
            if ch.isdigit():
                out.append(_DIGIT_WORD.get(ch, ch))
            elif ch == ".":
                out.append("point")
            elif ch == "-":
                out.append("minus")
            elif ch == "+":
                out.append("plus")
            else:
                out.append(ch)
        return " ".join(out)
    return s


class _ToSpoken(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._out: list[str] = []
        self._mode: list[str] = []  # "", "sub", "sup"
        # design/339 — italic depth, kept apart from the sub/sup stack so an
        # italic inside a subscript does not change how the subscript is read.
        self._ital = 0

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        t = tag.lower()
        if t in ("sub", "sup"):
            self._mode.append(t)
        elif t in ("i", "em", "br"):
            if t == "br":
                self._out.append(" ")
            else:
                self._ital += 1
        # 기타 태그 무시

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in ("sub", "sup") and self._mode and self._mode[-1] == t:
            self._mode.pop()
        elif t in ("i", "em") and self._ital > 0:
            self._ital -= 1

    def handle_data(self, data: str) -> None:
        if not data:
            return
        mode = self._mode[-1] if self._mode else ""
        if mode == "sub":
            # Keep numeric subscripts as digits so H2O can match a common name.
            raw = data.strip()
            if re.fullmatch(r"\d+", raw):
                self._out.append(raw)
            else:
                spoken = _speak_numberish(data)
                if spoken:
                    self._out.append(f" {spoken} ")
        elif mode == "sup":
            spoken = _speak_numberish(data)
            if spoken:
                self._out.append(f" to the {spoken} ")
        elif self._ital and re.fullmatch(r"[A-Za-z]", data.strip()):
            # design/339 — italics mark a variable. `<i>C</i> is the concentration`
            # was read as "carbon is the concentration", and `<i>K</i><sub>obs</sub>`
            # as "potassium observed". The letter is the name here.
            self._out.append(f"{VAR_MARK}{data.strip()}{VAR_MARK}")
        else:
            self._out.append(data)

    def get_text(self) -> str:
        return "".join(self._out)


def _apply_symbols(text: str) -> str:
    s = text
    for raw, spoken in _SYMBOL_SPOKEN:
        if raw in s:
            s = s.replace(raw, spoken)
    return s


_UNI_SUB = str.maketrans("₀₁₂₃₄₅₆₇₈₉₊₋₌", "0123456789+-=")
_UNI_SUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼", "0123456789+-=")


def _expand_unicode_scripts(text: str) -> str:
    """이미 유니코드 첨자인 경우 말로 풀기."""
    s = text

    def _sub_run(m: re.Match[str]) -> str:
        ascii_ = m.group(0).translate(_UNI_SUB)
        return f" {_speak_numberish(ascii_)} "

    def _sup_run(m: re.Match[str]) -> str:
        ascii_ = m.group(0).translate(_UNI_SUP)
        return f" to the {_speak_numberish(ascii_)} "

    s = re.sub(r"[₀₁₂₃₄₅₆₇₈₉₊₋₌]+", _sub_run, s)
    s = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼]+", _sup_run, s)
    return s


def _expand_plain_chem_digits(text: str) -> str:
    """
    Tag-free H2O / CO2 / BaZr0.9 — digits after element symbols.
    Skip Fig.2 / Table3 / B2B / COVID19-style tokens (design/205).
    """

    def _repl(m: re.Match[str]) -> str:
        el, num = m.group(1), m.group(2)
        start = m.start()
        prefix = text[max(0, start - 12) : start].lower()
        if re.search(
            r"(?:fig(?:ure)?|table|eq(?:uation)?|ref|sec(?:tion)?)\.?\s*$",
            prefix,
        ):
            return m.group(0)
        window = text[max(0, start - 4) : m.end() + 4]
        if re.search(r"\b[A-Z]{2,}\d+[A-Z0-9]*\b", window):
            return m.group(0)
        return f"{el} {_speak_numberish(num)} "

    return re.sub(
        r"(?<![a-z])([A-Z][a-z]?)(\d+(?:\.\d+)?)",
        _repl,
        text,
    )


def _expand_element_symbols(text: str) -> str:
    """
    Ni → nickel, Fe → iron.
    WHY: Cloud TTS는 Ni를 글자·이상한 음절로 읽음.
    He/As/In 등 영어 단어와 겹치면 화학식 맥락에서만 치환.
    """
    s = text
    for sym in _ELEMENT_KEYS_LONGEST:
        name = _ELEMENT_SPOKEN[sym]
        # design/339 — a single capital standing as its own word is a variable or a
        # label, not an element: in a formula the symbol is glued to digits or to
        # other symbols. Without this, `spoken_text_for_tts` was not idempotent —
        # the italic variable in `<i>K</i><sub>obs</sub>` resolves to `K observed`,
        # and a second pass turned that into `potassium observed`. Measured on the
        # ten-paper corpus: **0 of 2,366** sentences change, so the restriction
        # costs nothing on real input and only bites re-processed text.
        if len(sym) == 1 or sym in _ELEMENT_BARE_SKIP:
            # In2O3, BeO — 다음이 숫자·대문자 원소 시작.
            # `N-doped` is an element too, and the dash pass has already turned the
            # hyphen into a space by the time this runs, so the composition words
            # have to be named explicitly.
            pat = (
                rf"(?<![A-Za-z]){re.escape(sym)}"
                rf"(?=\d|[A-Z]|[₀-₉]|\s+{_ELEMENT_CONTEXT_WORD})"
            )
        else:
            # Ni catalyst, NiO — 소문자로 이어지는 보통 단어는 제외
            pat = rf"(?<![A-Za-z]){re.escape(sym)}(?![a-z])"
        s = re.sub(pat, f" {name} ", s)
    return s

# design/341 — singular and plural for the unit-run reader. Only unambiguous, high
# frequency tokens: a bare `C`, `F` or `N` after a number is as likely to be an
# element, Celsius or a sample name as it is a unit.
_UNIT_NAME: dict[str, tuple[str, str]] = {
    "m": ("meter", "meters"),
    "mm": ("millimeter", "millimeters"),
    "cm": ("centimeter", "centimeters"),
    "nm": ("nanometer", "nanometers"),
    "µm": ("micrometer", "micrometers"),
    "μm": ("micrometer", "micrometers"),
    "um": ("micrometer", "micrometers"),
    "km": ("kilometer", "kilometers"),
    "g": ("gram", "grams"),
    "mg": ("milligram", "milligrams"),
    "kg": ("kilogram", "kilograms"),
    "L": ("liter", "liters"),
    "mL": ("milliliter", "milliliters"),
    "s": ("second", "seconds"),
    "min": ("minute", "minutes"),
    "h": ("hour", "hours"),
    "mol": ("mole", "moles"),
    "K": ("kelvin", "kelvin"),
    "J": ("joule", "joules"),
    "kJ": ("kilojoule", "kilojoules"),
    "eV": ("electronvolt", "electronvolts"),
    "Pa": ("pascal", "pascals"),
    "Hz": ("hertz", "hertz"),
    "bar": ("bar", "bar"),
}
_UNIT_POWER = {2: "square ", 3: "cubic "}
_UNI_SUP_DIGIT = {"\u00b2": "2", "\u00b3": "3", "\u00b9": "1", "\u2070": "0"}
_UNIT_TOK = "|".join(
    sorted((re.escape(k) for k in _UNIT_NAME), key=len, reverse=True)
)
_UNIT_EXP_PART = r"(?:<sup>\s*([\u2212\-]?\d)\s*</sup>|([\u00b2\u00b3])|\u207b([\u00b9\u00b2\u00b3]))"
_UNIT_ITEM = rf"(?:{_UNIT_TOK})(?:{_UNIT_EXP_PART})?"
_UNIT_RUN = re.compile(
    # `>` and `<` are excluded so a subscript body like `<sub>2g</sub>` is not read
    # as "2 grams" — that is design/328's orbital label, not a unit.
    rf"(?<![A-Za-z0-9>])(?P<num>\d[\d.,]*)\s*"
    rf"(?P<run>{_UNIT_ITEM}(?:\s*[\u00b7\u22c5/]\s*{_UNIT_ITEM})*)"
    # A plain-text inverse (`cm-1`) belongs to the older unit table, which already
    # reads it as "per centimeter". Taking the token here would strand the `-1`.
    rf"(?![A-Za-z0-9<])(?!\s*[-\u2212\u2010\u2011]\s*\d)"
)
_UNIT_ITEM_RE = re.compile(rf"(?P<sep>^|[\u00b7\u22c5/])\s*(?P<tok>{_UNIT_TOK}){_UNIT_EXP_PART}?")
# Only take over a single plain token when the existing rules demonstrably miss it.
# `s` is deliberately absent: `O 1s` is an orbital, and "1 seconds" would be wrong.
_UNIT_PLAIN_OK = frozenset({"mm", "cm", "nm", "µm", "μm", "um", "mL", "m", "L", "g"})


def _unit_phrase(name: tuple[str, str], exp: int) -> str:
    singular, plural = name
    power = _UNIT_POWER.get(abs(exp), "")
    if exp < 0:
        return f"per {power}{singular}"
    return f"{power}{plural}"


def _read_unit_run(run: str) -> str | None:
    """`m²·g⁻¹` → "square meters per gram" (design/341).

    `·` separates units, it does not multiply them; `_apply_symbols` turned it into
    " times ", which is how an area per mass came out as "m times per gram".
    """
    items: list[tuple[str, int]] = []
    pos = 0
    for m in _UNIT_ITEM_RE.finditer(run):
        if m.start() != pos:
            return None
        pos = m.end()
        tok = m.group("tok")
        raw_exp = m.group(3) or m.group(4) or m.group(5)
        exp = 1
        if raw_exp:
            digit = _UNI_SUP_DIGIT.get(raw_exp, raw_exp)
            exp = int(str(digit).replace("\u2212", "-"))
            if m.group(5):  # a `⁻` prefix carried the sign
                exp = -abs(exp)
        if m.group("sep") == "/":
            exp = -abs(exp)
        items.append((tok, exp))
    if pos != len(run) or not items:
        return None
    if len(items) == 1 and items[0][1] == 1 and items[0][0] not in _UNIT_PLAIN_OK:
        return None
    positives = [_unit_phrase(_UNIT_NAME[t], e) for t, e in items if e > 0]
    negatives = [_unit_phrase(_UNIT_NAME[t], e) for t, e in items if e < 0]
    return " ".join(positives + negatives).strip() or None


def _expand_unit_runs(text: str) -> str:
    def _repl(m: re.Match[str]) -> str:
        spoken = _read_unit_run(re.sub(r"\s+", "", m.group("run")))
        if not spoken:
            return m.group(0)
        return f"{m.group('num')} {spoken} "

    return _UNIT_RUN.sub(_repl, text or "")


def _expand_units(text: str) -> str:
    """SI/energy units → spoken quantities before element names (design/88+90)."""
    s = text
    for pat, spoken in _UNIT_SPOKEN_RES:
        s = pat.sub(spoken, s)
    return s

_DOTTED_ABBREV = tuple(
    sorted((k for k in ACRONYM_SPOKEN if k.endswith(".")), key=len, reverse=True)
)


def _expand_dotted_abbrev(text: str) -> str:
    s = text or ""
    for key in _DOTTED_ABBREV:
        s = re.sub(
            rf"(?<![A-Za-z]){re.escape(key)}(?![A-Za-z])",
            f" {ACRONYM_SPOKEN[key]} ",
            s,
        )
    return s


def _mark_paper_terms(text: str, terms: dict[str, str] | None) -> tuple[str, list[str]]:
    """Claim this paper's own compound names on the printed form (design/343).

    Longest key first, so `CoFe2O4` is not eaten by a shorter `Co` entry. Returns the
    marked text and the spoken forms in index order; the marks join `freeze`'s
    mapping once it exists.
    """
    if not terms:
        return text or "", []
    s = text or ""
    spoken_by_index: list[str] = []
    for printed in sorted(terms, key=len, reverse=True):
        if not printed or printed not in s:
            continue
        idx = len(spoken_by_index)
        spoken_by_index.append(terms[printed])
        s = s.replace(printed, f"{_TERM_MARK}{idx}{_TERM_MARK}")
    return s, spoken_by_index


def _freeze_marked_terms(
    text: str, mapping: dict[str, str], spoken_by_index: list[str]
) -> str:
    def _repl(m: re.Match[str]) -> str:
        i = int(m.group(1))
        spoken = spoken_by_index[i] if 0 <= i < len(spoken_by_index) else ""
        key = f"\x00{len(mapping)}\x00"
        mapping[key] = spoken
        return key

    return _TERM_MARKED.sub(_repl, text or "")


def _mark_supplementary_labels(text: str) -> str:
    """`Fig. S1`, and then the `S7` in `Figs. S1 to S7` (design/339).

    The element pass read those as sulfur. A label word proves the first one; once a
    sentence is talking about supplementary items, a bare `S<n>` token in it is one
    too, which is what `to S7` and `S1 to S5` need.
    """
    s = text or ""
    marked, n = _SUPP_LABEL.subn(
        lambda m: f"{m.group(1)}{m.group(2)}{VAR_MARK}S{VAR_MARK}", s
    )
    if n or _SUPP_CONTEXT.search(s):
        marked = _SUPP_BARE.sub(lambda m: f"{VAR_MARK}S{VAR_MARK}{m.group(1)}", marked)
    return marked


def _freeze_marked_letters(text: str, mapping: dict[str, str]) -> str:
    """Hand marked variable/label letters to the existing freeze mapping (design/339).

    `freeze` already owns the placeholder namespace and `restore` already reverses
    it, so marked letters join that mapping instead of inventing a second one.
    """

    def _repl(m: re.Match[str]) -> str:
        key = f"\x00{len(mapping)}\x00"
        mapping[key] = m.group(1)
        return key

    return _VAR_MARKED.sub(_repl, text or "")


def _speak_prose_slash(text: str) -> str:
    """A slash is not a word (design/339, design/341).

    Between two lowercase words it is a pause: `adsorption/desorption`. Between
    symbols or numbers it is a ratio, which a reader says as "over" — the corpus's
    single most repeated speech defect was `STY CH4/STY CO2`, spoken with the slash
    intact seven times in one paper. A URL is left alone: breaking it up would hide
    that it should not be practice text at all (design/340).
    """
    s = text or ""
    if "http" in s or "www." in s:
        return s
    s = re.sub(r"(?<=[a-z])\s*/\s*(?=[a-z])", ", ", s)
    return re.sub(r"(?<=[A-Za-z0-9])\s*/\s*(?=[A-Za-z0-9])", " over ", s)


def _strip_literal_tags(text: str) -> str:
    """EDGE: escaped/failed markup left as visible tags — do not speak 'sub'."""
    return _LITERAL_TAG_RE.sub(" ", text)


def _fold_formula_subscripts(text: str) -> str:
    """H₂O / CO₂ → H2O / CO2 so the common-name lexicon can see them."""
    return re.sub(
        r"([A-Za-z])([₀₁₂₃₄₅₆₇₈₉]+)",
        lambda m: m.group(1) + m.group(2).translate(_UNI_SUB),
        text or "",
    )


def _apply_chem_aliases(text: str) -> str:
    """Whole-formula common names. Longest key, not a raw substring (CO2 inside CH3CO2H)."""
    s = text
    for grapheme in sorted(CHEM_ALIASES.keys(), key=len, reverse=True):
        spoken = CHEM_ALIASES[grapheme]
        pat = re.compile(
            rf"(?<![A-Za-z0-9]){re.escape(grapheme)}(?![A-Za-z0-9])"
        )
        s = pat.sub(f" {spoken} ", s)
    return s


def _formula_token(token: str) -> bool:
    if token in FORMULA_FRAGMENTS or token in CHEM_ALIASES:
        return True
    if re.fullmatch(r"[A-Z][a-z]{3,}", token):
        return False
    if re.search(r"\d", token):
        return True
    # PhOH / GaN — not an English word.
    return bool(re.search(r"[A-Z].*[A-Z]", token)) and not re.search(
        r"[a-z]{3,}", token
    )


def _split_formula_fragments(token: str) -> str:
    keys = tuple(sorted(FORMULA_FRAGMENTS, key=len, reverse=True))
    i = 0
    parts: list[str] = []
    hit = False
    while i < len(token):
        for key in keys:
            if token.startswith(key, i):
                parts.append(f" {FORMULA_FRAGMENTS[key]} ")
                i += len(key)
                hit = True
                break
        else:
            parts.append(token[i])
            i += 1
    if not hit:
        return token
    return "".join(parts)


def _apply_formula_fragments(text: str) -> str:
    """Name a fragment only after the whole formula missed the common-name list."""

    def _repl(m: re.Match[str]) -> str:
        token = m.group(0)
        if not _formula_token(token):
            return token
        if token in CHEM_ALIASES:
            return token
        return _split_formula_fragments(token)

    return re.sub(
        r"(?<![A-Za-z])[A-Z][A-Za-z0-9]{0,24}(?![A-Za-z0-9])",
        _repl,
        text or "",
    )


def _letter_spell_unknown_caps(text: str) -> str:
    """All-caps technique names that are not a known word → letters, not elements."""

    def _repl(m: re.Match[str]) -> str:
        word = m.group(0)
        if word in ACRONYM_SPOKEN or word in CHEM_ALIASES:
            return word
        return " ".join(ch.lower() for ch in word)

    return re.sub(r"\b[A-Z]{2,}\b", _repl, text or "")


def _collapse_full_name_abbrev(text: str) -> str:
    """Prefer one form when full name and acronym co-occur (design/205)."""

    def _name_matches(abbr: str, name: str) -> bool:
        hints = ACRONYM_NAME_HINTS.get(abbr)
        if not hints:
            return False
        low = name.lower()
        return any(h in low for h in hints)

    def _repl_name_abbr(m: re.Match[str]) -> str:
        name, abbr = m.group(1).strip(), m.group(2)
        if _name_matches(abbr, name):
            return name
        return m.group(0)

    def _repl_abbr_name(m: re.Match[str]) -> str:
        abbr, name = m.group(1), m.group(2).strip()
        if not _name_matches(abbr, name):
            return m.group(0)
        return name

    s = text
    s = re.sub(
        r"\b([A-Za-z][A-Za-z0-9\s\-/,]{2,80}?)\s*\(([A-Z][A-Z0-9\-]{1,12})\)",
        _repl_name_abbr,
        s,
    )
    s = re.sub(
        r"\b([A-Z][A-Z0-9\-]{1,12})\s*\(([A-Za-z][^)]{2,80})\)",
        _repl_abbr_name,
        s,
    )
    return s


def _expand_acronyms(text: str) -> str:
    """Lexicon acronyms to spoken (longest keys first)."""
    s = text
    for key in sorted(ACRONYM_SPOKEN.keys(), key=len, reverse=True):
        spoken = ACRONYM_SPOKEN[key]
        if key.endswith("."):
            pat = re.compile(rf"(?<![A-Za-z]){re.escape(key)}(?![A-Za-z])")
        else:
            pat = re.compile(rf"\b{re.escape(key)}\b")
        s = pat.sub(f" {spoken} ", s)
    return s



# design/217 — link dash vs minus (practice ear-form)
_UMINUS_TOKEN = ""  # private-use; must not match element symbols
_LINK_DASH_CLS = r"\-\u2010\u2011\u2013\u2014"  # hyphen / en / em (not U+2212 minus)
# design/342 — the placeholder `freeze` wraps a decided token in.
_FROZEN_MARK = "\x00"
_ANY_DASH_SCRUB = re.compile(rf"[{_LINK_DASH_CLS}\u2212]")


def _dash_pass_a(text: str) -> str:
    """Protect unary minus; silence link hyphens; narrow ranges → to."""
    s = text or ""
    # Unary minus / hyphen-minus before a digit (not mid-token alnum).
    # design/342 — `\x00` is a frozen token, so the hyphen in a sample code such as
    # `BZY10-1700` sits between two parts of one name, not in front of a negative
    # number. Without excluding it the reader heard "B Z Y 10 minus 1700", and that
    # code appears 32 times in one paper. A real range keeps its digits visible
    # (`10-1700 K`), so it is untouched.
    s = re.sub(rf"(?<![A-Za-z0-9.{_FROZEN_MARK}])[\u2212\-](?=\d)", _UMINUS_TOKEN, s)
    s = re.sub(r"([=:+/(])\s*[\u2212\-](?=\d)", rf"\1{_UMINUS_TOKEN}", s)

    # OCR decade powers 10-3 -> spoken inverse (not a numeric range; design/217)
    s = re.sub(r"\b10[\u2212\-]([1-6])\b", r"10 to the minus \1", s)

    # Single-letter pairs: F-T, I-V, C-H, P-N
    s = re.sub(
        rf"\b([A-Z])[{_LINK_DASH_CLS}]([A-Z])\b",
        r"\1 \2",
        s,
    )
    # Compound / alloy / temper links: Ni-Cu, N-doped, 6061-T6, well-known
    s = re.sub(
        rf"(?<=[A-Za-z0-9)\]])[{_LINK_DASH_CLS}](?=[A-Za-z])",
        " ",
        s,
    )
    s = re.sub(
        rf"(?<=\d)[{_LINK_DASH_CLS}](?=[A-Za-z])",
        " ",
        s,
    )

    # Narrow ranges → to (never 10-3 decade OCR; never letter alloys)
    s = re.sub(
        rf"(?i)(\bpH\s+)(\d+)\s*[{_LINK_DASH_CLS}\u2212]\s*(\d+)",
        r"\1\2 to \3",
        s,
    )
    s = re.sub(
        rf"(\d+)\s*[{_LINK_DASH_CLS}\u2212]\s*(\d+)(?=\s*(?:wt\s*)?%)",
        r"\1 to \2",
        s,
        flags=re.IGNORECASE,
    )

    def _yearish_range(m: re.Match[str]) -> str:
        a, b = m.group(1), m.group(2)
        if a == "10" and b in set("123456"):
            return m.group(0)
        # design/342 — a grant number is not a range: `award DMR 08-019762` was
        # read as "08 to 019762". A printed range never carries a leading zero.
        if (len(a) > 1 and a.startswith("0")) or (len(b) > 1 and b.startswith("0")):
            return m.group(0)
        return f"{a} to {b}"

    s = re.sub(
        # design/342 — not a range when the left number is the tail of a frozen
        # token: `BZY10-1700` is one sample code. The hyphen then falls through to
        # the link-dash scrub and goes silent, which is how `BZY10-ZnO` already
        # reads. A printed range keeps its digits visible and still says "to".
        rf"(?<!{_FROZEN_MARK})(\d{{2,}})\s*[{_LINK_DASH_CLS}\u2212]\s*(\d{{2,}})",
        _yearish_range,
        s,
    )
    return s


def _dash_pass_b(text: str) -> str:
    """Letter-speak single-letter pairs before element expand (F T → f t)."""

    def _pair(m: re.Match[str]) -> str:
        return f"{m.group(1).lower()} {m.group(2).lower()}"

    return re.sub(r"\b([A-Z]) ([A-Z])\b", _pair, text or "")


def _dash_pass_c(text: str) -> str:
    """Scrub leftover spaced/link dashes; restore unary minus word."""
    s = text or ""
    s = re.sub(rf"\s+[{_LINK_DASH_CLS}\u2212]\s+", " ", s)
    s = re.sub(
        rf"(?<=[A-Za-z])[{_LINK_DASH_CLS}](?=[A-Za-z])",
        " ",
        s,
    )
    s = s.replace(_UMINUS_TOKEN, " minus ")
    return s


def _apply_light_prosody(text: str) -> str:
    """Punctuation-first pauses for Neural2 (design/205)."""
    s = text
    s = re.sub(r"\bgoes to\b", "goes to,", s, flags=re.IGNORECASE)
    s = re.sub(r"\bequilibrium\b", "equilibrium,", s, flags=re.IGNORECASE)
    s = re.sub(r",\s*,+", ", ", s)
    return s


_FORMULA_PAREN = re.compile(
    r"^(?:"
    r"[IVX]{1,4}"
    r"|aq|[sgl]"
    r"|OH|CO|NO|NH|SO|PO|CN|Cl|Br"
    r"|(?:[A-Z][a-z]?)*\d+"
    r"|\d{3}"
    r")$"
)


_ROMAN_SPOKEN = {
    "II": "two",
    "III": "three",
    "IV": "four",
    "VI": "six",
}


def _keep_formula_paren(inner: str) -> bool:
    """(NO3), (III), (110), (COOH) are the formula. Prose asides are not."""
    t = (inner or "").strip()
    if not t or any(ch.isspace() for ch in t) or len(t) > 12:
        return False
    if t in FORMULA_FRAGMENTS or t in CHEM_ALIASES or t in _ROMAN_SPOKEN:
        return True
    if not re.search(r"[A-Za-z]", t) and not re.fullmatch(r"\d{3}", t):
        return False
    return bool(_FORMULA_PAREN.fullmatch(t))


def _paren_duplicates_before(before: str, inner: str) -> bool:
    """Drop (CO2) after carbon dioxide, or (CVD) after the words it abbreviates."""
    t = (inner or "").strip()
    letters = [c for c in t if c.isalpha()]
    if re.fullmatch(r"[A-Z][A-Z0-9]{1,12}", t) and len(letters) >= 2:
        words = re.findall(r"[A-Za-z]+", before)
        if len(words) >= len(letters):
            tail = words[-len(letters) :]
            if [w[0].upper() for w in tail] == [c.upper() for c in letters]:
                return True
    spoken = CHEM_ALIASES.get(t) or FORMULA_FRAGMENTS.get(t) or _ELEMENT_SPOKEN.get(t)
    if not spoken:
        return False
    words = re.findall(r"[A-Za-z]+", before)
    name_words = spoken.split()
    if len(words) < len(name_words):
        return False
    got = " ".join(words[-len(name_words) :]).lower()
    return got == spoken.lower()


def _drop_parenthetical_asides(text: str) -> str:
    """Omit parenthetical asides from speech. Keep formula groups."""
    s = text or ""
    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch not in "()（）":
            out.append(ch)
            i += 1
            continue
        close = "）" if ch == "（" else ")"
        if ch in "）)":
            out.append(ch)
            i += 1
            continue
        depth = 1
        j = i + 1
        while j < n and depth:
            if s[j] == ch:
                depth += 1
            elif s[j] == close:
                depth -= 1
            j += 1
        if depth:
            out.append(s[i:])
            break
        inner = s[i + 1 : j - 1]
        kept = inner.strip()
        if _keep_formula_paren(kept) and not _paren_duplicates_before("".join(out), kept):
            spoken_inner = _ROMAN_SPOKEN.get(kept, kept)
            out.append(f" {spoken_inner} ")
        i = j
    s = "".join(out)
    s = re.sub(r"\s+([,.;:])", r"\1", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()


def _paren_drop_ranges(text: str) -> list[tuple[int, int]]:
    """Display ranges of parentheses that speech drops. End is exclusive."""
    s = text or ""
    dropped: list[tuple[int, int]] = []
    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch not in "()（）":
            out.append(ch)
            i += 1
            continue
        close = "）" if ch == "（" else ")"
        if ch in "）)":
            out.append(ch)
            i += 1
            continue
        depth = 1
        j = i + 1
        while j < n and depth:
            if s[j] == ch:
                depth += 1
            elif s[j] == close:
                depth -= 1
            j += 1
        if depth:
            break
        kept = s[i + 1 : j - 1].strip()
        keep = _keep_formula_paren(kept) and not _paren_duplicates_before(
            "".join(out), kept
        )
        if keep:
            out.append(f" {_ROMAN_SPOKEN.get(kept, kept)} ")
        else:
            dropped.append((i, j))
        i = j
    return dropped


def _match_spoken_slice(full: str, cursor: int, piece: str) -> int | None:
    piece_n = re.sub(r"\s+", " ", piece).strip()
    if not piece_n:
        return cursor
    i = cursor
    pi = 0
    while pi < len(piece_n) and i < len(full):
        if piece_n[pi].isspace():
            if not full[i].isspace():
                return None
            while pi < len(piece_n) and piece_n[pi].isspace():
                pi += 1
            while i < len(full) and full[i].isspace():
                i += 1
            continue
        if full[i].casefold() != piece_n[pi].casefold():
            return None
        i += 1
        pi += 1
    if pi != len(piece_n):
        return None
    return i


def _take_one_spoken_word(full: str, cursor: int) -> int | None:
    """End of the spoken word at [cursor], or None when there is none left."""
    i = cursor
    n = len(full)
    while i < n and full[i].isspace():
        i += 1
    start = i
    while i < n and not full[i].isspace():
        i += 1
    return i if i > start else None


def _char_class(ch: str) -> str:
    if ch.isdigit():
        return "digit"
    if ch.isalpha():
        return "upper" if ch.isupper() else "lower"
    if ch.isspace():
        return "space"
    if ch in "-‐‑‒–—―":
        return "dash"
    if ch in ".,;:!?":
        return "punct"
    if ch in "()[]{}":
        return "paren"
    if ch == "'":
        return "apos"
    return "symbol"


def _token_shape(token: str) -> str:
    has_digit = any(ch.isdigit() for ch in token)
    has_alpha = any(ch.isalpha() for ch in token)
    if has_digit and has_alpha:
        return "alnum"
    if has_digit:
        return "digits"
    if "'" in token:
        return "apos"
    if has_alpha:
        return "letters"
    return "other"


def _gap_shape(gap: str) -> str:
    kinds = {_char_class(ch) for ch in gap if not ch.isspace()}
    if not kinds:
        return "space" if gap else "none"
    if len(kinds) == 1:
        return next(iter(kinds))
    return "mixed"


def _differ_at(full: str, cursor: int, piece: str) -> tuple[int, str, str]:
    piece_n = re.sub(r"\s+", " ", piece).strip()
    i = cursor
    pi = 0
    while pi < len(piece_n) and i < len(full):
        if piece_n[pi].isspace():
            if not full[i].isspace():
                return pi, _char_class(full[i]), "space"
            while pi < len(piece_n) and piece_n[pi].isspace():
                pi += 1
            while i < len(full) and full[i].isspace():
                i += 1
            continue
        if full[i] != piece_n[pi]:
            return pi, _char_class(full[i]), _char_class(piece_n[pi])
        i += 1
        pi += 1
    if pi != len(piece_n):
        nxt = _char_class(piece_n[pi]) if pi < len(piece_n) else "end"
        return pi, "end", nxt
    return -1, "none", "none"


def _align_report(
    *,
    code: str,
    spans: list[dict[str, int]],
    token_i: int,
    cursor: int,
    display_chars: int,
    spoken_chars: int,
    token_len: int = -1,
    piece_len: int = -1,
    differ_at: int = -1,
    token_shape: str = "none",
    piece_class: str = "none",
    full_class: str = "none",
    gap_len: int = -1,
    gap_shape: str = "none",
    matched_n: int = 0,
    tail_n: int = 0,
    renamed_n: int = 0,
) -> dict[str, object]:
    return {
        "code": code,
        "spans": spans,
        "token_i": token_i,
        "cursor": cursor,
        "display_chars": display_chars,
        "spoken_chars": spoken_chars,
        "token_len": token_len,
        "piece_len": piece_len,
        "differ_at": differ_at,
        "token_shape": token_shape,
        "piece_class": piece_class,
        "full_class": full_class,
        "gap_len": gap_len,
        "gap_shape": gap_shape,
        "matched_n": matched_n,
        "tail_n": tail_n,
        "renamed_n": renamed_n,
    }


def _keep_matched_spans(
    spans: list[dict[str, int]], full: str, cursor: int
) -> list[dict[str, int]]:
    """Matched words stay. A zero-width tail weight keeps the audio clock honest."""
    kept = list(spans)
    remain = len(full) - cursor
    if remain > 0:
        kept.append({"start": 0, "end": 0, "weight": remain})
    return kept


def align_display_report(
    display: str, *, spoken: str | None = None
) -> dict[str, object]:
    """Why printed words did or did not line up with the spoken form.

    Counts and a short code only. No sentence text.
    ``code`` is ``ok``, ``empty_display``, ``empty_spoken``,
    ``token_unmatched``, or ``trailing_residue``.
    A failed code still keeps spans for the words that already matched.
    ``spoken``, when passed, is the same string the caller will play.
    """
    raw = (display or "").strip()
    if not raw:
        return _align_report(
            code="empty_display",
            spans=[],
            token_i=-1,
            cursor=0,
            display_chars=0,
            spoken_chars=0,
        )
    full = spoken if spoken is not None else spoken_text_for_tts(raw)
    if not full.strip():
        return _align_report(
            code="empty_spoken",
            spans=[],
            token_i=-1,
            cursor=0,
            display_chars=len(raw),
            spoken_chars=len(full),
        )
    dropped = _paren_drop_ranges(raw)
    word = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z]+)?")
    matches = list(word.finditer(raw))
    spans: list[dict[str, int]] = []
    cursor = 0
    token_i = -1
    prev_end = 0
    renamed_n = 0

    def _skip_ws() -> None:
        nonlocal cursor
        while cursor < len(full) and full[cursor].isspace():
            cursor += 1

    def _matched_n() -> int:
        return sum(1 for span in spans if int(span.get("weight") or 0) > 0 and int(span.get("end") or 0) > int(span.get("start") or 0))

    for token_i, m in enumerate(matches):
        start, end = m.start(), m.end()
        inside = any(a <= start and end <= b for a, b in dropped)
        if inside:
            spans.append({"start": start, "end": end, "weight": 0})
            prev_end = end
            continue
        token = m.group(0)
        piece = spoken_text_for_tts(_ROMAN_SPOKEN.get(token, token))
        piece_n = re.sub(r"\s+", " ", piece).strip()
        _skip_ws()
        # A comma or similar mark is not the next word. Skipping it lets the
        # rest of a longer chunk stay in the score.
        if piece_n and (piece_n[0].isalnum() or piece_n[0] == "'"):
            while cursor < len(full) and not (
                full[cursor].isalnum() or full[cursor] == "'"
            ):
                cursor += 1
                _skip_ws()
        matched = _match_spoken_slice(full, cursor, piece)
        if matched is None:
            # The printed word is read as another word (`nm` -> nanometers,
            # `1` -> one). Take the next spoken word so the rest of the
            # sentence keeps its light, phones and score slots.
            matched = _take_one_spoken_word(full, cursor)
            if matched is not None:
                renamed_n += 1
        if matched is None:
            differ_at, full_class, piece_class = _differ_at(full, cursor, piece)
            return _align_report(
                code="token_unmatched",
                spans=_keep_matched_spans(spans, full, cursor),
                token_i=token_i,
                cursor=cursor,
                display_chars=len(raw),
                spoken_chars=len(full),
                token_len=len(token),
                piece_len=len(piece_n),
                differ_at=differ_at,
                token_shape=_token_shape(token),
                piece_class=piece_class,
                full_class=full_class,
                gap_len=max(0, start - prev_end),
                gap_shape=_gap_shape(raw[prev_end:start]),
                matched_n=_matched_n(),
                tail_n=len(matches) - token_i,
                renamed_n=renamed_n,
            )
        weight = matched - cursor
        spans.append({"start": start, "end": end, "weight": max(weight, 1)})
        cursor = matched
        prev_end = end
    _skip_ws()
    # A final period is not a word. Leaving it unmatched dropped every span.
    while cursor < len(full) and not (full[cursor].isalnum() or full[cursor] == "'"):
        cursor += 1
        _skip_ws()
    if cursor != len(full):
        return _align_report(
            code="trailing_residue",
            spans=_keep_matched_spans(spans, full, cursor),
            token_i=token_i,
            cursor=cursor,
            display_chars=len(raw),
            spoken_chars=len(full),
            matched_n=_matched_n(),
            tail_n=0,
            renamed_n=renamed_n,
            full_class=_char_class(full[cursor]) if cursor < len(full) else "end",
        )
    return _align_report(
        code="ok",
        spans=spans,
        renamed_n=renamed_n,
        token_i=token_i,
        cursor=cursor,
        display_chars=len(raw),
        spoken_chars=len(full),
        matched_n=_matched_n(),
        tail_n=0,
    )


def align_display_to_spoken(display: str) -> list[dict[str, int]]:
    """Printed-word spans for follow light. Empty list means do not light."""
    report = align_display_report(display)
    spans = report["spans"]
    return spans if isinstance(spans, list) else []


def spoken_text_for_tts(
    raw: str,
    *,
    policy: SpeakPolicy | None = None,
    terms: dict[str, str] | None = None,
) -> str:
    """
    Display HTML/plain -> English spoken for TTS (design/205 · 216 · 217 · 326).

    `terms` is the paper's own spoken dictionary (design/326 hybrid). It wins over
    every built-in rule, so a formula this module would only spell can be given
    the name the authors actually say.
    """
    _ = policy or load_speak_policy()
    s = (raw or "").strip()
    if not s:
        return ""

    if "&" in s:
        # design/326 — extraction can double-escape, so `&amp;gt;` needs two
        # rounds. One pass left `&gt;` to be read aloud as an entity.
        for _ in range(3):
            after = html_lib.unescape(s)
            if after == s:
                break
            s = after

    # design/343 — the paper's own names win, and they have to be claimed while the
    # printed form is intact: after the HTML parse, `Ba<sub>0.5</sub>` is words.
    s, _term_spoken = _mark_paper_terms(s, terms)
    # design/341 — read unit runs while the printed form is still regular. Doing it
    # here also keeps the exponent away from the citation rule, which deleted a
    # positive one: `259.1 m²·g⁻¹` came out as "259.1 m times per gram".
    s = _expand_unit_runs(s)
    # design/328 — mark a variable's exponent before the citation rule can eat it.
    s = protect_variable_exponents(s)
    # design/216 — strip numeric cite <sup>n</sup> before HTML->spoken
    s = strip_cite_markers_for_display(s)

    if "<" in s:
        parser = _ToSpoken()
        try:
            parser.feed(s)
            parser.close()
            s = parser.get_text()
        except Exception:  # noqa: BLE001
            s = re.sub(r"<[^>]+>", " ", s)

    s = _strip_literal_tags(s)
    s = resolve_variable_exponents(s)
    # design/326 — rejoin sub/superscripts first. The HTML parser spaces them out,
    # and a spaced `Ba0.5 Sr0.5 ... O3` is not recognisable as one formula, so the
    # token decisions below would never see it.
    s = _fold_formula_subscripts(s)
    # design/326 — drop the section prefix before anything freezes it. `Title:`
    # opens with the titanium symbol, so the proper-noun guard would keep it.
    s = _SECTION_PREFIX.sub("", s)
    # design/326 — say the long form and the abbreviation. Must precede the aside
    # drop, which would otherwise delete the definition.
    s = voice_definitions(s)
    # design/326 — decide acronyms, site labels and namable compounds once, then
    # hide them so no later pass can split an acronym into element symbols. This
    # sits before the unicode-script pass, which turns a trailing delta into a
    # word and would split the formula token in two.
    # design/339 — `Fig. S1` is a supplementary label, and the element pass turned
    # its S into sulfur ("figure sulfur 1"). Mark it before anything can rename it.
    s = _mark_supplementary_labels(s)
    # design/339 — `Figs.` reached TTS intact and was read as the fruit. `freeze`
    # takes `Figs` for a proper noun before the acronym lexicon can see it, so the
    # dotted abbreviations are expanded ahead of the freeze rather than after it.
    s = _expand_dotted_abbrev(s)
    s, _frozen = freeze(s, terms=terms)
    s = _freeze_marked_letters(s, _frozen)
    s = _freeze_marked_terms(s, _frozen, _term_spoken)
    s = _expand_unicode_scripts(s)
    s = _drop_parenthetical_asides(s)
    s = _apply_chem_aliases(s)
    s = _apply_formula_fragments(s)
    s = _expand_plain_chem_digits(s)
    s = _collapse_full_name_abbrev(s)
    # design/217 — dash A, then units before symbols (cm−1)
    s = _dash_pass_a(s)
    s = _expand_units(s)
    s = _apply_symbols(s)
    # Acronyms before elements so NMR is not nitrogen+MR (design/205).
    s = _expand_acronyms(s)
    s = _dash_pass_b(s)
    s = _letter_spell_unknown_caps(s)
    s = _expand_element_symbols(s)
    s = _dash_pass_c(s)
    s = _apply_light_prosody(s)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.strip(" 	\"'`")
    s = restore(s, _frozen)
    # design/326 — units, ranges and punctuation the way a speaker says them.
    s = spoken_post(s)
    s = _speak_prose_slash(s)
    s = restore_sentence_case(s, raw or "")
    return s
