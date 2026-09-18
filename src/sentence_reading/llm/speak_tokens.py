"""
design/326 — decide the spoken form per token, then freeze it.

Why this exists
---------------
`tts_speak.spoken_text_for_tts` was a single line of ~20 regex passes. Each pass
could re-chew what an earlier pass produced, so the same kind of token got
different treatment depending on which pass reached it first:

    CNT   -> "c n t"                  (acronym guard hit)
    CNTs  -> "carbon nitrogen Ts"     (plural s defeated the guard, element pass ate C and N)
    SACs  -> "sulfur ACs"
    NPs   -> "nitrogen Ps"
    B-site-> "boron site"             (B is a lattice position, not boron)
    NiO   -> "nickel oxygen"          (a name composed from parts, chemically wrong)

This module runs first, decides the spoken form for the spans it is sure about,
and replaces them with opaque placeholders the later passes cannot touch. The
decision is made once, by kind, so one kind of token has one behaviour.

Practice-mode rules this encodes (design/326):
  - Never compose a chemical name from parts. If the name is not known, spell
    the symbols. `NiO` is "nickel oxide" or "N I O", never "nickel oxygen".
  - An acronym is atomic, plural `s` included. Never split it into elements.
  - A single capital before `-site` / ` site` is a lattice position, not an element.
  - Prefer what a speaker says, which is usually shorter than the expansion.
  - Never change or drop a value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Placeholder cannot appear in paper text and survives \s+ collapsing.
_SENTINEL = "\x00"
_PLACEHOLDER = re.compile(r"\x00(\d+)\x00")

# Element symbol -> spoken name, for the compositional namer only.
_METAL_NAME: dict[str, str] = {
    "Ag": "silver",
    "Al": "aluminum",
    "Ba": "barium",
    "Bi": "bismuth",
    "Ca": "calcium",
    "Cd": "cadmium",
    "Ce": "cerium",
    "Co": "cobalt",
    "Cr": "chromium",
    "Cs": "cesium",
    "Cu": "copper",
    "Fe": "iron",
    "Ga": "gallium",
    "Gd": "gadolinium",
    "Hf": "hafnium",
    "In": "indium",
    "Ir": "iridium",
    "K": "potassium",
    "La": "lanthanum",
    "Li": "lithium",
    "Mg": "magnesium",
    "Mn": "manganese",
    "Mo": "molybdenum",
    "Na": "sodium",
    "Nb": "niobium",
    "Nd": "neodymium",
    "Ni": "nickel",
    "Pb": "lead",
    "Pd": "palladium",
    "Pr": "praseodymium",
    "Pt": "platinum",
    "Rh": "rhodium",
    "Ru": "ruthenium",
    "Sb": "antimony",
    "Sc": "scandium",
    "Si": "silicon",
    "Sn": "tin",
    "Sr": "strontium",
    "Ta": "tantalum",
    "Ti": "titanium",
    "V": "vanadium",
    "W": "tungsten",
    "Y": "yttrium",
    "Zn": "zinc",
    "Zr": "zirconium",
}

# Whole formula -> the name a speaker uses. Extends CHEM_ALIASES with the
# compounds observed in real papers that the old table missed.
COMPOUND_NAME: dict[str, str] = {
    "HNO3": "nitric acid",
    "HCOOH": "formic acid",
    "H3PO4": "phosphoric acid",
    "NaBH4": "sodium borohydride",
    "KOH": "potassium hydroxide",
    "NaCl": "sodium chloride",
    "Fe3O4": "magnetite",
    "Al2O3": "alumina",
    "SiO2": "silica",
    "TiO2": "titania",
    "ZrO2": "zirconia",
    "CeO2": "ceria",
    "MgO": "magnesia",
    "MgAl2O4": "magnesium aluminate",
    "NiAl2O4": "nickel aluminate",
    "FeAl2O4": "iron aluminate",
    "N2O": "nitrous oxide",
    "H2S": "hydrogen sulfide",
    "NH4OH": "ammonium hydroxide",
    "NH4NO3": "ammonium nitrate",
    "(NH4)2SO4": "ammonium sulfate",
    "NaHCO3": "sodium bicarbonate",
    "Na2CO3": "sodium carbonate",
    "CaCO3": "calcium carbonate",
    "BaCO3": "barium carbonate",
    "La2O3": "lanthana",
    "Y2O3": "yttria",
    "Cr2O3": "chromia",
    "Co3O4": "cobalt oxide",
    "Mn3O4": "manganese oxide",
    "WO3": "tungsten oxide",
    "MoO3": "molybdenum oxide",
    "V2O5": "vanadium oxide",
}

# Anion suffix patterns: (regex on the tail, spoken suffix)
_ANION_SUFFIX: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^\(NO3\)(\d*)$"), "nitrate"),
    (re.compile(r"^\(OH\)(\d*)$"), "hydroxide"),
    (re.compile(r"^\(SO4\)(\d*)$"), "sulfate"),
    (re.compile(r"^\(CO3\)(\d*)$"), "carbonate"),
    (re.compile(r"^\(PO4\)(\d*)$"), "phosphate"),
    (re.compile(r"^NO3$"), "nitrate"),
    (re.compile(r"^SO4$"), "sulfate"),
    (re.compile(r"^CO3$"), "carbonate"),
    (re.compile(r"^Cl(\d*)$"), "chloride"),
    (re.compile(r"^O(\d*)$"), "oxide"),
    (re.compile(r"^S(\d*)$"), "sulfide"),
    (re.compile(r"^N(\d*)$"), "nitride"),
    (re.compile(r"^C(\d*)$"), "carbide"),
]

_SUP_DIGITS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
_SUB_DIGITS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")

_DIGIT_WORD = {
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
}

# `C 1s`, `O 2p`, `Ni 2p3` — a core level, not the element plus a number.
_XPS = re.compile(r"(?<![A-Za-z])([A-Z][a-z]?)\s+(\d)([spdf])\b")

# `JEM-2200FS`, `TGP-H-090` — an instrument or model label. The trailing letters
# are a suffix, not elements: `2200FS` was read as "2200 fluorine sulfur".
# The hyphen is what distinguishes a model label from a formula: `JEM-2200FS`
# has one, `CH4` and `Ni(NO3)2` do not and must stay chemicals.
_MODEL = re.compile(
    r"(?<![A-Za-z0-9])([A-Z]{2,}[-\u2010\u2011]\d+[A-Z]{0,3})(?![A-Za-z0-9])"
)

# A capitalised word whose first one or two letters are an element symbol but
# which continues as a word: Kröger, Nafion, Tafel, Fischer, Barrett.
_PROPER_WORD = re.compile(
    r"(?<![A-Za-z])"
    r"(?:H|B|C|N|O|F|P|S|K|V|W|Y|I|He|Li|Be|Ne|Na|Mg|Al|Si|Cl|Ar|Ca|Sc|Ti|Cr"
    r"|Mn|Fe|Co|Ni|Cu|Zn|Ga|Ge|As|Se|Br|Kr|Rb|Sr|Zr|Nb|Mo|Ru|Rh|Pd|Ag|Cd|In"
    r"|Sn|Sb|Te|Xe|Cs|Ba|La|Ce|Pr|Nd|Ta|Re|Os|Ir|Pt|Au|Hg|Tl|Pb|Bi|Th|U)"
    r"[a-z\u00c0-\u024f]{3,}"
    r"(?![A-Za-z])"
)


@dataclass(frozen=True)
class Decided:
    printed: str
    spoken: str
    kind: str


def letter_spell(token: str) -> str:
    """`CNT` -> `C N T`, `CNTs` -> `C N Ts`. Case kept so prosody survives."""
    core = token
    tail = ""
    if len(core) > 1 and core[-1] == "s" and core[:-1].isupper():
        core, tail = core[:-1], "s"
    letters = " ".join(core)
    return f"{letters}{tail}" if tail else letters


def _norm_scripts(s: str) -> str:
    return s.translate(_SUP_DIGITS).translate(_SUB_DIGITS)


def compound_name(formula: str) -> str | None:
    """The spoken name for a formula, or None when it is not safe to name one.

    Returning None is the important half: the caller then spells the symbols
    rather than composing something the paper does not say.
    """
    f = _norm_scripts((formula or "").strip())
    if not f:
        return None
    if f in COMPOUND_NAME:
        return COMPOUND_NAME[f]
    # The pre-existing alias table stays authoritative for what it covers.
    from sentence_reading.llm.tts_speak_lexicon import CHEM_ALIASES

    if f in CHEM_ALIASES:
        return CHEM_ALIASES[f]

    # A single metal followed by one anion group: Ni(NO3)2, Fe2O3, IrO2, NiCl2.
    m = re.match(r"^([A-Z][a-z]?)(\d*)(\(?[A-Z][A-Za-z0-9]*\)?\d*)$", f)
    if m:
        metal, _count, tail = m.group(1), m.group(2), m.group(3)
        name = _METAL_NAME.get(metal)
        if name:
            for pat, suffix in _ANION_SUFFIX:
                if pat.match(tail):
                    return f"{name} {suffix}"
    return None


def _spell_formula(formula: str) -> str:
    """`FeOx` -> `F E O X`. Digits stay digits so no value changes."""
    out: list[str] = []
    for ch in _norm_scripts(formula):
        if ch.isalpha():
            out.append(ch.upper())
        elif ch.isdigit() or ch == ".":
            out.append(ch)
        elif ch in "()":
            continue
        else:
            out.append(ch)
    joined = " ".join(c for c in out if c.strip())
    joined = re.sub(r"\s+", " ", joined).strip()
    # `B Z Y 1 0` reads as one-zero. Keep a multi-digit number whole: `B Z Y 10`.
    return re.sub(r"(?<=\d) (?=\d)", "", joined)


def _is_complex_formula(f: str) -> bool:
    """Doped or fractional formulas: too long to say, prefer symbols."""
    norm = _norm_scripts(f)
    if re.search(r"\d+\.\d+", norm):
        return True
    # Three or more element symbols has no single spoken name a reader expects
    # (LaNiO3, NiCo2O4). Spelling them is honest; composing a name is not.
    return len(re.findall(r"[A-Z][a-z]?", norm)) >= 3


# `N M R` produced by an earlier call. Keep it, do not re-chew it.
_SPELLED_RUN = re.compile(r"(?<![A-Za-z])[A-Z](?: [A-Z])+s?(?![A-Za-z])")
# `F-T`, `I-V`, `C-H` — single capitals joined by hyphens are letter pairs, not
# elements and not a minus (design/217). Decided here so the result is stable.
_CAP_PAIR = re.compile(
    r"(?<![A-Za-z])([A-Z](?:[-\u2010\u2011\u2013][A-Z])+)(?![A-Za-z-])"
)

# `Pt/C`, `H2/CO` — decided before the element passes see either side.
# The right side may open with a Greek prefix (`Ni/γ-Al2O3`), which is a support.
_SLASH_PAIR = re.compile(
    r"(?<![A-Za-z0-9/])"
    r"((?:[A-Z][a-z]?\d*){1,6})\s*/\s*"
    r"(?:[\u03b1-\u03c9]\s*[-\u2010\u2011\u2013]?\s*)?"
    r"((?:[A-Z][a-z]?\d*){1,6})"
    r"(?![A-Za-z0-9/])"
)
# A slash between units is `per`, and the unit lexicon already handles it.
# `Wh/L` is energy density, not a chemical pair (design/90).
_UNIT_TOKENS = {
    "A", "Ah", "C", "F", "G", "Hz", "J", "K", "L", "M", "N", "Pa", "S", "T",
    "V", "W", "Wh", "cm", "g", "h", "kg", "kJ", "km", "m", "mA", "mAh", "mg",
    "min", "mL", "mM", "mm", "mol", "ms", "mV", "nm", "s", "um", "\u03bcm",
}

# `Ba0.5Sr0.5Co0.8Fe0.2O3` style, and simple binary/ternary formulas.
_FORMULA = re.compile(
    r"(?<![A-Za-z0-9])"
    r"((?:[A-Z][a-z]?(?:\d+(?:\.\d+)?)?|\((?:[A-Z][a-z]?\d*)+\)\d*){2,}"
    r"(?:[-\u2212\u2013]?[\u03b4x])?)"
    r"(?![A-Za-z])"
)
# Acronym: two or more capitals, optional plural s, optional hyphenated run.
# A trailing digit means it is a formula, not an acronym (HNO3 is not `H N O`),
# so the formula pass must have had its turn first.
_ACRONYM = re.compile(
    r"(?<![A-Za-z0-9])([A-Z]{2,}(?:-[A-Z]{2,})*s?)(?![A-Za-z0-9])"
)
# A lattice position, not an element: `B-site`, `B'-site`, `A site`.
_SITE = re.compile(r"(?<![A-Za-z])([A-Z]['\u2032]?)[-\u2010\u2011\u2013 ]site\b")
# Orbital labels: t2g, eg, with an optional exponent.
_ORBITAL = re.compile(
    r"(?<![A-Za-z])(t2g|eg)(?:\^?(~?\d+(?:\.\d+)?))?(?![A-Za-z])"
)


def _orbital_spoken(label: str, exp: str | None) -> str:
    base = "t two g" if label == "t2g" else "e g"
    if not exp:
        return base
    if exp.startswith("~"):
        return f"{base} about {exp[1:]}"
    return f"{base} {exp}"


def freeze(
    text: str,
    *,
    terms: dict[str, str] | None = None,
) -> tuple[str, dict[str, str]]:
    """Decide the sure spans and hide them behind placeholders.

    Returns the masked text and the placeholder -> spoken mapping. Order matters:
    the paper's own term dictionary wins, then acronyms (so an acronym is never
    exposed to the element rules), then site labels, then formulas.
    """
    mapping: dict[str, str] = {}

    def _put(spoken: str) -> str:
        key = f"{_SENTINEL}{len(mapping)}{_SENTINEL}"
        mapping[key] = spoken
        return key

    s = text or ""

    # 0. An already-spelled run stays as it is. Without this, a second call
    #    lowercases `N M R` to `n m R` and the transform is not idempotent.
    s = _SPELLED_RUN.sub(lambda m: _put(m.group(0)), s)

    # 1. Paper term dictionary (design/326 hybrid: filled at ingest).
    for printed in sorted(terms or {}, key=len, reverse=True):
        spoken = (terms or {})[printed]
        if not printed.strip() or not spoken.strip():
            continue
        s = re.sub(
            r"(?<![A-Za-z0-9])" + re.escape(printed) + r"(?![A-Za-z0-9])",
            lambda _m, _sp=spoken: _put(_sp),
            s,
        )

    # 2. Site labels before anything can read the capital as an element.
    s = _SITE.sub(lambda m: _put(f"{m.group(1)[0].upper()} site"), s)

    # 2b. Hyphenated single capitals: `F-T` is "F T", never fluorine or a minus.
    s = _CAP_PAIR.sub(
        lambda m: _put(" ".join(re.findall(r"[A-Z]", m.group(1)))), s
    )

    # 2c. A capitalised word that merely opens with an element symbol is a name,
    #     not a chemical. `Kröger` was read as "krypton öger", `Nafion` risks
    #     "sodium fion". Freeze it as printed.
    s = _PROPER_WORD.sub(lambda m: _put(m.group(0)), s)

    # 2c2. Instrument and model labels keep their digits and spell their letters.
    s = _MODEL.sub(
        lambda m: _put(
            re.sub(
                r"\s+",
                " ",
                " ".join(
                    part if part.isdigit() else " ".join(part)
                    for part in re.findall(r"\d+|[A-Z]+", m.group(1))
                ),
            )
        ),
        s,
    )

    # 2d. XPS / orbital notation: `C 1s` is "C one s", not "carbon 1s".
    s = _XPS.sub(
        lambda m: _put(f"{m.group(1)} {_DIGIT_WORD.get(m.group(2), m.group(2))} {m.group(3)}"),
        s,
    )

    # 3. Orbital labels.
    s = _ORBITAL.sub(
        lambda m: _put(_orbital_spoken(m.group(1), m.group(2))), s
    )

    # 4. A slash between two chemical tokens: support is "on", ratio is "to".
    #    Units keep their own `per` handling (design/90 — Wh/L is not a pair).
    def _slash(m: re.Match[str]) -> str:
        left, right = m.group(1), m.group(2)
        # `Wh/L` is a unit over a unit. `Pt/C` is a metal on a support, and `C`
        # is carbon here, so only the left side decides.
        if left in _UNIT_TOKENS:
            return m.group(0)
        joiner = "on" if right in _SUPPORTS else "to"
        return f"{_decide(left, _put)} {joiner} {_decide(right, _put)}"

    s = _SLASH_PAIR.sub(_slash, s)

    # 5. Formulas before acronyms: HNO3 is a formula, not `H N O` plus a stray 3.
    def _form(m: re.Match[str]) -> str:
        tok = m.group(1)
        if _has_named_fragment(tok) and not compound_name(tok):
            return tok  # the fragment lexicon reads it better than spelling
        return _decide(tok, _put)

    s = _FORMULA.sub(_form, s)

    # 6. Whatever all-caps runs remain are acronyms, plural included.
    def _acr(m: re.Match[str]) -> str:
        tok = m.group(1)
        if tok in _UNIT_TOKENS:
            return tok
        if _has_named_fragment(tok) and not compound_name(tok):
            return tok
        return _decide(tok, _put)

    s = _ACRONYM.sub(_acr, s)
    return s, mapping


def _has_named_fragment(token: str) -> bool:
    """`RCOOH` reads better as `R carboxyl` than as spelled letters."""
    from sentence_reading.llm.tts_speak_lexicon import FORMULA_FRAGMENTS

    norm = _norm_scripts(token)
    return any(frag in norm for frag in FORMULA_FRAGMENTS)


def _decide(token: str, put) -> str:
    """One token, one decision: known name, else spelled symbols."""
    named = compound_name(token)
    if named:
        return put(named)
    # A doped, fractional formula has no good deterministic reading: spelling
    # `Ba0.5Sr0.5...` gives "B A 0. 5 S R 0. 5" which is worse than the legacy
    # expansion. This is the case the paper's own term dictionary must answer
    # (design/326 Phase 2 — the authors call it BSCF). Leave it alone until then.
    if _has_fraction(token):
        return token
    # A bare element symbol is the element. `Pt/C` is platinum on carbon.
    elem = _element_name(token)
    if elem:
        return put(elem)
    if _looks_like_formula(token):
        return put(_spell_formula(token))
    return put(letter_spell(token))


_NONMETAL_NAME = {
    "C": "carbon",
    "N": "nitrogen",
    "O": "oxygen",
    "H": "hydrogen",
    "S": "sulfur",
    "P": "phosphorus",
    "B": "boron",
    "F": "fluorine",
    "Cl": "chlorine",
    "Br": "bromine",
    "I": "iodine",
    "He": "helium",
    "Ne": "neon",
    "Ar": "argon",
    "Kr": "krypton",
    "Xe": "xenon",
    "Se": "selenium",
    "Te": "tellurium",
    "As": "arsenic",
    "Ge": "germanium",
}


def _element_name(token: str) -> str | None:
    t = (token or "").strip()
    if t in _METAL_NAME:
        return _METAL_NAME[t]
    return _NONMETAL_NAME.get(t)


def _has_fraction(token: str) -> bool:
    return bool(re.search(r"\d+\.\d+", _norm_scripts(token or "")))


def _looks_like_formula(token: str) -> bool:
    norm = _norm_scripts(token)
    return bool(re.search(r"\d", norm)) or bool(
        re.match(r"^(?:[A-Z][a-z][A-Za-z0-9()]*)$", norm)
    )


_DEF_PAREN = re.compile(r"\s*\(([A-Z][A-Za-z0-9\-]{1,15}s?)\)")
_STOPWORD = {
    "of",
    "the",
    "and",
    "in",
    "on",
    "for",
    "to",
    "a",
    "an",
    "with",
    "by",
    "at",
}


def _initials_match(words: list[str], acronym: str) -> bool:
    """Do the preceding words spell this acronym? `TPR` after
    `temperature programmed reduction` does."""
    core = acronym[:-1] if acronym.endswith("s") and acronym[:-1].isupper() else acronym
    letters = [c for c in core if c.isalpha()]
    if len(letters) < 2:
        return False
    cand = [w for w in words if w.lower() not in _STOPWORD]
    tail = cand[-len(letters):]
    if len(tail) < len(letters):
        return False
    return all(
        w[:1].lower() == c.lower() for w, c in zip(tail, letters, strict=False)
    )


def voice_definitions(text: str) -> str:
    """design/326 P4 — say the long form and the abbreviation, not just one.

    `temperature-programmed reduction (TPR)` becomes
    `temperature-programmed reduction, T P R`. This has to run before the
    parenthetical-aside drop, which used to delete the abbreviation outright and
    leave later sentences using letters the listener never heard defined.
    """

    def _sub(m: re.Match[str]) -> str:
        acr = m.group(1)
        if not any(c.isupper() for c in acr):
            return m.group(0)
        before = text[: m.start()]
        words = re.findall(r"[A-Za-z][A-Za-z\-]*", before)[-8:]
        flat: list[str] = []
        for w in words:
            flat.extend(p for p in w.split("-") if p)
        if not _initials_match(flat, acr):
            return m.group(0)
        # Hand back a bare comma plus the abbreviation; `freeze` runs next and
        # will letter-spell it once, so no later pass can lowercase it.
        return f", {acr}"

    return _DEF_PAREN.sub(_sub, text)


_UNIT_WORD: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?<=\d)\s*\u2103"), " degrees Celsius"),
    (re.compile(r"(?<=\d)\s*\u00b0\s*C(?![a-z])"), " degrees Celsius"),
    # A bare degree with no C is an angle, not a temperature.
    (re.compile(r"(?<=\d)\s*\u00b0(?![A-Za-z])"), " degrees"),
    (re.compile(r"(?<=\d)\s+M(?![A-Za-z])"), " molar"),
    (re.compile(r"(?<=\d)\s+mol(?![A-Za-z])"), " molar"),
    (re.compile(r"(?<![\d.])1\s+min(?![A-Za-z])"), "1 minute"),
    (re.compile(r"(?<=\d)\s+min(?![A-Za-z])"), " minutes"),
    (re.compile(r"(?<![\d.])1\s+h(?![A-Za-z])"), "1 hour"),
    (re.compile(r"(?<=\d)\s+h(?![A-Za-z])"), " hours"),
    (re.compile(r"(?<![\d.])1\s+s(?![A-Za-z])"), "1 second"),
    (re.compile(r"(?<=\d)\s+s(?![A-Za-z])"), " seconds"),
    (re.compile(r"(?<=\d)\s*wt\s*%"), " weight percent"),
    (re.compile(r"(?<=\d)\s*at\s*%"), " atomic percent"),
    (re.compile(r"(?<=\d)\s+kV(?![A-Za-z])"), " kilovolts"),
    (re.compile(r"(?<=\d)\s+mg(?![A-Za-z])"), " milligrams"),
    (re.compile(r"(?<=\d)\s+kg(?![A-Za-z])"), " kilograms"),
    (re.compile(r"(?<=\d)\s+mL(?![A-Za-z])"), " milliliters"),
    (re.compile(r"(?<=\d)\s+(?:um|\u03bcm)(?![A-Za-z])"), " micrometers"),
    (re.compile(r"(?<=\d)\s+nm(?![A-Za-z])"), " nanometers"),
    (re.compile(r"(?<=\d)\s+rpm(?![A-Za-z])"), " r p m"),
    # `~` before a number is spoken, not shown.
    (re.compile(r"~\s*(?=[\d.])"), "about "),
]

# `mV/decade`, `mL/s` — a unit over anything is `per`.
_UNIT_SLASH = re.compile(
    r"(?<![A-Za-z0-9])((?:m|k|M|G|n|u|\u03bc)?(?:V|A|L|g|s|m|W|J|Hz|mol|Pa))"
    r"\s*/\s*([A-Za-z]+)(?![A-Za-z0-9])"
)
_UNIT_WORDS_SPOKEN = (
    "volt|millivolt|ampere|milliampere|gram|milligram|kilogram|second|minute|"
    "hour|kelvin|liter|milliliter|watt|joule|kilojoule|mole|molar|meter|"
    "centimeter|millimeter|nanometer|micrometer|degree|degrees|coulomb|farad|"
    "hertz|pascal|bar|electron volt"
)
_UNIT_WORD_SLASH = re.compile(
    rf"(?<![A-Za-z])({_UNIT_WORDS_SPOKEN})s?\s*/\s*([a-z]+)(?![A-Za-z])"
)

# `Pt/C`, `Pt/CNT` — a metal on a support is spoken "on".
_SUPPORTS = (
    "C",
    "CNT",
    "CNTs",
    "MgO",
    "SiO2",
    "TiO2",
    "ZrO2",
    "CeO2",
    "Al2O3",
    "MgAl2O4",
)


def spoken_post(text: str) -> str:
    """Units, ranges, slashes and punctuation the way a speaker says them."""
    s = text or ""
    for pat, word in _UNIT_WORD:
        s = pat.sub(word, s)
    s = _UNIT_SLASH.sub(r"\1 per \2", s)
    # By now the abbreviations are words, so `millivolt /decade` needs the same
    # treatment. Only a known unit word on the left may claim `per`.
    s = _UNIT_WORD_SLASH.sub(r"\1 per \2", s)
    # A slash between two plain numbers is a ratio: `1/60` is "1 to 60".
    s = re.sub(r"(?<![A-Za-z0-9.])(\d+)\s*/\s*(\d+)(?![A-Za-z0-9.])", r"\1 to \2", s)
    # `> 87%` is spoken, not shown.
    s = re.sub(r"(?<![A-Za-z])>\s*(?=[\d.])", "greater than ", s)
    s = re.sub(r"(?<![A-Za-z])<\s*(?=[\d.])", "less than ", s)
    # A dash between two numbers that share a unit is a range.
    s = re.sub(r"(?<=\d)\s*[-\u2010\u2011\u2013](?=\d)", " to ", s)
    # `0.25 volt -1.00 volt` — the unit word sits between the two numbers, so the
    # dash is still a range. A bare `at -5` is not, and must keep its minus.
    s = re.sub(
        r"(\d[\d.]*\s+[a-z]+)\s*[-\u2010\u2011\u2013\u2212]\s*(?=\d)",
        r"\1 to ",
        s,
    )
    # No space before closing punctuation; TTS pauses on it otherwise.
    s = re.sub(r"\s+([,.;:!?])", r"\1", s)
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\s+\)", ")", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()


def slash_by_meaning(text: str) -> str:
    """`Pt/C` -> `platinum on carbon`; `H2/CO` -> `hydrogen to carbon monoxide`."""
    def _sub(m: re.Match[str]) -> str:
        left, right = m.group(1), m.group(2)
        joiner = "on" if right in _SUPPORTS else "to"
        return f"{left} {joiner} {right}"

    return re.sub(
        r"(?<![A-Za-z0-9])([A-Z][A-Za-z0-9]*)\s*/\s*([A-Z][A-Za-z0-9]*)(?![A-Za-z0-9])",
        _sub,
        text or "",
    )


def restore(text: str, mapping: dict[str, str]) -> str:
    if not mapping:
        return text
    # A hyphen that joined a formula to a frozen token is not spoken:
    # `H2-TPR` is "hydrogen T P R", `Fe-Ni` is "iron nickel".
    s = re.sub(r"[-\u2010\u2011\u2013]\s*(?=\x00)", " ", text or "")
    s = re.sub(r"(\x00\d+\x00)\s*[-\u2010\u2011\u2013](?=\s|$)", r"\1 ", s)

    def _sub(m: re.Match[str]) -> str:
        return mapping.get(m.group(0), "")

    return _PLACEHOLDER.sub(_sub, s)


def restore_sentence_case(spoken: str, source: str) -> str:
    """Keep the printed sentence's opening capital so prosody survives."""
    if not spoken or not source:
        return spoken
    src = source.lstrip()
    if not src or not src[0].isupper():
        return spoken
    for i, ch in enumerate(spoken):
        if ch.isalpha():
            if ch.isupper():
                return spoken
            return spoken[:i] + ch.upper() + spoken[i + 1 :]
        if ch not in " \t\"'(":
            break
    return spoken
