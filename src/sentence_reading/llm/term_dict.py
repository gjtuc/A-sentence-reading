"""design/343 — the paper's own names for its compounds, verified before use.

design/326 chose to spell a three-or-more-element formula letter by letter, because
"composing a name is not honest", and named the paper's own term dictionary as the
answer (Phase 2). `spoken_text_for_tts(..., terms=...)` and `freeze(..., terms=...)`
were built for it and no caller ever filled them.

The survey already asks Gemini for the paper's formulas once per ingest, so the
names come from the same call. What is new here is the **gate**: a wrong name is
worse than spelled letters, because the reader hears a fact that is not in the paper.
`CoFe2O4` read as "cobalt oxide" loses the iron and nothing would disagree.

So a proposed name is accepted only when it accounts for exactly the elements the
formula contains — either by naming them, or by being the authors' own initialism.
"""

from __future__ import annotations

import re

# Element symbol -> spoken element name, for checking a proposal.
_SYMBOL_NAME: dict[str, str] = {
    "H": "hydrogen",
    "Li": "lithium",
    "Be": "beryllium",
    "B": "boron",
    "C": "carbon",
    "N": "nitrogen",
    "O": "oxygen",
    "F": "fluorine",
    "Na": "sodium",
    "Mg": "magnesium",
    "Al": "aluminum",
    "Si": "silicon",
    "P": "phosphorus",
    "S": "sulfur",
    "Cl": "chlorine",
    "K": "potassium",
    "Ca": "calcium",
    "Sc": "scandium",
    "Ti": "titanium",
    "V": "vanadium",
    "Cr": "chromium",
    "Mn": "manganese",
    "Fe": "iron",
    "Co": "cobalt",
    "Ni": "nickel",
    "Cu": "copper",
    "Zn": "zinc",
    "Ga": "gallium",
    "Ge": "germanium",
    "As": "arsenic",
    "Se": "selenium",
    "Br": "bromine",
    "Rb": "rubidium",
    "Sr": "strontium",
    "Y": "yttrium",
    "Zr": "zirconium",
    "Nb": "niobium",
    "Mo": "molybdenum",
    "Ru": "ruthenium",
    "Rh": "rhodium",
    "Pd": "palladium",
    "Ag": "silver",
    "Cd": "cadmium",
    "In": "indium",
    "Sn": "tin",
    "Sb": "antimony",
    "Te": "tellurium",
    "I": "iodine",
    "Cs": "cesium",
    "Ba": "barium",
    "La": "lanthanum",
    "Ce": "cerium",
    "Pr": "praseodymium",
    "Nd": "neodymium",
    "Sm": "samarium",
    "Eu": "europium",
    "Gd": "gadolinium",
    "Tb": "terbium",
    "Dy": "dysprosium",
    "Ho": "holmium",
    "Er": "erbium",
    "Yb": "ytterbium",
    "Hf": "hafnium",
    "Ta": "tantalum",
    "W": "tungsten",
    "Re": "rhenium",
    "Os": "osmium",
    "Ir": "iridium",
    "Pt": "platinum",
    "Au": "gold",
    "Hg": "mercury",
    "Tl": "thallium",
    "Pb": "lead",
    "Bi": "bismuth",
    "Th": "thorium",
    "U": "uranium",
}

# A name fragment and the elements it accounts for. An `-ate`/`-ite` anion carries
# oxygen, which is why `cobalt ferrite` explains the O in `CoFe2O4`.
_NAME_STEM: dict[str, frozenset[str]] = {
    "ferrite": frozenset({"Fe", "O"}),
    "ferric": frozenset({"Fe"}),
    "ferrous": frozenset({"Fe"}),
    "magnetite": frozenset({"Fe", "O"}),
    "hematite": frozenset({"Fe", "O"}),
    "cuprate": frozenset({"Cu", "O"}),
    "cupric": frozenset({"Cu"}),
    "titanate": frozenset({"Ti", "O"}),
    "titania": frozenset({"Ti", "O"}),
    "zirconate": frozenset({"Zr", "O"}),
    "zirconia": frozenset({"Zr", "O"}),
    "aluminate": frozenset({"Al", "O"}),
    "alumina": frozenset({"Al", "O"}),
    "molybdate": frozenset({"Mo", "O"}),
    "tungstate": frozenset({"W", "O"}),
    "stannate": frozenset({"Sn", "O"}),
    "niobate": frozenset({"Nb", "O"}),
    "tantalate": frozenset({"Ta", "O"}),
    "vanadate": frozenset({"V", "O"}),
    "chromate": frozenset({"Cr", "O"}),
    "chromite": frozenset({"Cr", "O"}),
    "manganate": frozenset({"Mn", "O"}),
    "manganite": frozenset({"Mn", "O"}),
    "cobaltite": frozenset({"Co", "O"}),
    "nickelate": frozenset({"Ni", "O"}),
    "cerate": frozenset({"Ce", "O"}),
    "silicate": frozenset({"Si", "O"}),
    "silica": frozenset({"Si", "O"}),
    "zeolite": frozenset(),
    "perovskite": frozenset(),
    "spinel": frozenset(),
    "sulfate": frozenset({"S", "O"}),
    "sulphate": frozenset({"S", "O"}),
    "sulfite": frozenset({"S", "O"}),
    "sulfide": frozenset({"S"}),
    "sulphide": frozenset({"S"}),
    "nitrate": frozenset({"N", "O"}),
    "nitrite": frozenset({"N", "O"}),
    "nitride": frozenset({"N"}),
    "phosphate": frozenset({"P", "O"}),
    "phosphide": frozenset({"P"}),
    "carbonate": frozenset({"C", "O"}),
    "carbide": frozenset({"C"}),
    "borate": frozenset({"B", "O"}),
    "boride": frozenset({"B"}),
    "bromate": frozenset({"Br", "O"}),
    "bromide": frozenset({"Br"}),
    "chlorate": frozenset({"Cl", "O"}),
    "chloride": frozenset({"Cl"}),
    "chloroplatinic": frozenset({"H", "Cl", "Pt"}),
    "iodide": frozenset({"I"}),
    "fluoride": frozenset({"F"}),
    "selenide": frozenset({"Se"}),
    "telluride": frozenset({"Te"}),
    "hydroxide": frozenset({"O", "H"}),
    "hydroxy": frozenset({"O", "H"}),
    "oxyhydroxide": frozenset({"O", "H"}),
    "hydride": frozenset({"H"}),
    "oxide": frozenset({"O"}),
    "dioxide": frozenset({"O"}),
    "trioxide": frozenset({"O"}),
    "monoxide": frozenset({"O"}),
    "peroxide": frozenset({"O"}),
    "water": frozenset({"H", "O"}),
    "ammonia": frozenset({"N", "H"}),
    "ammonium": frozenset({"N", "H"}),
    "graphene": frozenset({"C"}),
    "graphite": frozenset({"C"}),
    # design/343 — acid names. `acid` itself carries the hydrogen, so
    # `sulfuric acid` accounts for H2SO4 exactly.
    "acid": frozenset({"H"}),
    "sulfuric": frozenset({"S", "O"}),
    "sulphuric": frozenset({"S", "O"}),
    "nitric": frozenset({"N", "O"}),
    "nitrous": frozenset({"N", "O"}),
    "phosphoric": frozenset({"P", "O"}),
    "carbonic": frozenset({"C", "O"}),
    "boric": frozenset({"B", "O"}),
    "hydrochloric": frozenset({"H", "Cl"}),
    "hydrofluoric": frozenset({"H", "F"}),
    "hydrobromic": frozenset({"H", "Br"}),
    "perchloric": frozenset({"Cl", "O"}),
    "acetic": frozenset({"C", "H", "O"}),
    "formic": frozenset({"C", "H", "O"}),
    "oxalic": frozenset({"C", "H", "O"}),
    "citric": frozenset({"C", "H", "O"}),
    # Hydrocarbons and small organics, which name their elements implicitly.
    "methane": frozenset({"C", "H"}),
    "ethane": frozenset({"C", "H"}),
    "propane": frozenset({"C", "H"}),
    "butane": frozenset({"C", "H"}),
    "ethylene": frozenset({"C", "H"}),
    "ethene": frozenset({"C", "H"}),
    "propylene": frozenset({"C", "H"}),
    "propene": frozenset({"C", "H"}),
    "acetylene": frozenset({"C", "H"}),
    "benzene": frozenset({"C", "H"}),
    "toluene": frozenset({"C", "H"}),
    "ethanol": frozenset({"C", "H", "O"}),
    "methanol": frozenset({"C", "H", "O"}),
    "propanol": frozenset({"C", "H", "O"}),
    "acetone": frozenset({"C", "H", "O"}),
    "acetaldehyde": frozenset({"C", "H", "O"}),
    "formaldehyde": frozenset({"C", "H", "O"}),
    "urea": frozenset({"C", "H", "N", "O"}),
    "glucose": frozenset({"C", "H", "O"}),
    "cellulose": frozenset({"C", "H", "O"}),
    "syngas": frozenset({"C", "O", "H"}),
}

# Words a name may carry that say nothing about composition.
_IGNORABLE = frozenset(
    {
        "the", "a", "an", "and", "of", "on", "in", "with", "single", "atom", "atoms",
        "doped", "dopant", "supported", "support", "nano", "nanoparticle",
        "nanoparticles", "nanosheet", "nanosheets", "catalyst", "catalysts", "phase",
        "mixed", "layered", "cubic", "hexagonal", "amorphous", "crystalline", "type",
        "based", "rich", "deficient", "activated", "reduced", "oxidized", "alloy",
        "solid", "solution", "powder", "film", "framework", "porous", "mesoporous",
        "gas", "aqueous",
        # `Fe@SiO2` is read "iron at silica" — core-shell notation, not a element.
        "at", "over", "core", "shell", "encapsulated", "confined", "anchored",
        "embedded", "decorated", "modified", "loaded",
        # design/343 — a charge reading: `Pt2+` is "platinum two ion". These words
        # say nothing about which elements are present, and refusing them threw
        # away correct names.
        "ion", "ions", "cation", "cations", "anion", "anions", "species", "state",
        "zero", "one", "two", "three", "four", "five", "six", "seven", "plus",
        "minus", "valent", "divalent", "trivalent", "tetravalent", "metallic",
    }
)

_SYMBOL_RE = re.compile(r"[A-Z][a-z]?")
_NAME_TO_SYMBOL = {name: sym for sym, name in _SYMBOL_NAME.items()}
_STEM_KEYS = tuple(sorted(_NAME_STEM, key=len, reverse=True))
# `δ`, `x`, `y` stand for a variable amount, not an element.
_VARIABLE = frozenset({"x", "y", "z", "\u03b4", "\u03b5"})


def formula_elements(raw: str) -> set[str]:
    """Element symbols in a printed formula, case-sensitively.

    Case is what separates `Co` (cobalt) from `CO` (carbon monoxide), so the parse
    only takes a two-letter symbol when the second letter is lower case.
    """
    text = re.sub(r"<[^>]+>", "", raw or "")
    text = re.sub(r"[\u2080-\u2089]", lambda m: str(ord(m.group(0)) - 0x2080), text)
    out: set[str] = set()
    i = 0
    while i < len(text):
        ch = text[i]
        if not ch.isupper():
            i += 1
            continue
        pair = text[i : i + 2]
        if len(pair) == 2 and pair[1].islower() and pair in _SYMBOL_NAME:
            out.add(pair)
            i += 2
            continue
        if ch in _SYMBOL_NAME:
            out.add(ch)
        i += 1
    return out


_TRIVIAL_OXIDE_MIN_STEM = 4


def _trivial_oxide_element(word: str) -> str | None:
    """`ceria`, `magnesia`, `baria` — an oxide named by trimming its element.

    A list of these is always one journal behind, and the pattern is regular: drop
    the trailing `a` and what is left is the start of the element's name. Requiring
    four characters keeps short accidents out.
    """
    if len(word) < _TRIVIAL_OXIDE_MIN_STEM + 1 or not word.endswith("a"):
        return None
    stem = word[:-1]
    if len(stem) < _TRIVIAL_OXIDE_MIN_STEM:
        return None
    for name, symbol in _NAME_TO_SYMBOL.items():
        if name.startswith(stem):
            return symbol
    return None


def name_elements(name: str) -> tuple[set[str], bool]:
    """Elements a proposed name accounts for, and whether every word was understood."""
    low = re.sub(r"[^a-z\s\-]", " ", (name or "").lower())
    found: set[str] = set()
    understood = True
    for word in re.split(r"[\s\-]+", low):
        if not word or word in _IGNORABLE:
            continue
        if word in _NAME_TO_SYMBOL:
            found.add(_NAME_TO_SYMBOL[word])
            continue
        # Chemical names carry composition in the **suffix** (`-oxide`, `-ferrite`,
        # `-titanate`), so a suffix match is the meaningful one. Matching anywhere in
        # the word let an unknown word inherit a stem it merely contained.
        hit = next((k for k in _STEM_KEYS if word.endswith(k)), None)
        if hit is not None:
            found |= _NAME_STEM[hit]
            continue
        trivial = _trivial_oxide_element(word)
        if trivial is not None:
            found |= {trivial, "O"}
            continue
        understood = False
    return found, understood


def _is_authors_initialism(formula: str, name: str) -> bool:
    """`Ba0.5Sr0.5Co0.8Fe0.2O3` called `BSCF` by its authors.

    Each letter must be the first letter of a distinct element, in the order the
    formula prints them. Oxygen is conventionally dropped, so the initialism may be
    shorter than the element list.
    """
    letters = re.sub(r"[^A-Za-z]", "", name or "")
    if not (2 <= len(letters) <= 6) or letters != letters.upper():
        return False
    text = re.sub(r"<[^>]+>", "", formula or "")
    order: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if not ch.isupper():
            i += 1
            continue
        pair = text[i : i + 2]
        if len(pair) == 2 and pair[1].islower() and pair in _SYMBOL_NAME:
            order.append(pair)
            i += 2
            continue
        if ch in _SYMBOL_NAME:
            order.append(ch)
        i += 1
    want = list(letters)
    for sym in order:
        if want and sym[0] == want[0]:
            want.pop(0)
    return not want


def verify_term(formula: str, spoken: str) -> bool:
    """Does this name account for exactly the formula's elements? (design/343)

    Equality both ways. A name that misses an element drops information the paper
    printed; a name that adds one invents chemistry.
    """
    if not (formula or "").strip() or not (spoken or "").strip():
        return False
    if re.fullmatch(r"[\s\w.\-]{0,3}", spoken.strip()):
        return False
    want = {s for s in formula_elements(formula) if s not in _VARIABLE}
    if not want:
        return False
    if _is_authors_initialism(formula, spoken):
        return True
    got, understood = name_elements(spoken)
    if not understood:
        return False
    return got == want


def build_term_dict(rows: list[dict]) -> tuple[dict[str, str], list[str]]:
    """Survey rows -> accepted `printed -> spoken`, plus the refused printed forms."""
    terms: dict[str, str] = {}
    refused: list[str] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        printed = str(row.get("raw") or "").strip()
        spoken = str(row.get("spoken") or "").strip()
        if not printed or not spoken:
            continue
        if printed.lower() == spoken.lower():
            continue
        if not verify_term(printed, spoken):
            refused.append(printed)
            continue
        terms[printed] = spoken
        # design/343 — papers print `Ba<sub>0.5</sub>…`, and by the time `freeze`
        # runs the tags are already spoken words, so a flattened key can never
        # match. The survey's `rich` field is the printed form, so it is a key too.
        rich = str(row.get("rich") or "").strip()
        if rich and rich != printed:
            terms[rich] = spoken
    return terms, refused
