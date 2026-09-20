# 343 — The paper's own compound names, verified before the reader hears them

**Version:** 0.3.338 · gate widened in 0.3.339 · Status: **locked**  
Fills [326](326-practice-speech-tokens.md) Phase 2 · follows [342](342-a-code-hyphen-is-not-a-minus.md)

## Why

design/326 chose to spell a three-or-more-element formula letter by letter:

> Three or more element symbols has no single spoken name a reader expects
> (LaNiO3, NiCo2O4). Spelling them is honest; composing a name is not.

That is a defensible product decision, and it left `CoFe2O4` as "C O F E 2 O 4",
where a listener cannot tell `Co` from `C O` or `Fe` from `F E`. design/326 named the
answer itself — the paper's own term dictionary, Phase 2 — and the hooks were already
built: `spoken_text_for_tts(..., terms=...)` and `freeze(..., terms=...)`, with
`freeze`'s own comment saying "the paper's own term dictionary wins".

**Nothing ever filled them.** And the survey that runs once per ingest was already
asking Gemini for the paper's formulas, using the answer only to restore subscripts.

## The gate is the point of this chip

A wrong name is worse than spelled letters. Letters are unhelpful; a wrong name is a
**fact the paper does not contain**, and nothing downstream would disagree —
`CoFe2O4` read as "cobalt oxide" silently loses the iron.

So a proposed name is accepted only when it accounts for **exactly** the elements the
formula contains, both directions: missing one drops what the paper printed, adding
one invents chemistry.

| formula | proposal | verdict |
|---|---|---|
| `CoFe2O4` | cobalt ferrite | Co, Fe, O all accounted → **accept** |
| `CoFe2O4` | cobalt oxide | Fe unaccounted → **refuse** |
| `Co3O4` | cobalt titanate | Ti is not in the formula → **refuse** |
| `CoFe2O4` | cobalt ferrite wurtzite | `wurtzite` names no element → **refuse** |
| `Ba0.5Sr0.5Co0.8Fe0.2O3` | BSCF | authors' initialism, in order → **accept** |

Element accounting needs two small facts of chemistry. An `-ate`/`-ite` anion carries
oxygen, which is why `cobalt ferrite` explains the O in `CoFe2O4`; and case is what
separates `Co` (cobalt) from `CO` (carbon monoxide), so the formula parse only takes
a two-letter symbol when the second letter is lower case.

Composition suffixes are matched as **suffixes**, not anywhere in the word. Matching
anywhere let an unknown word inherit a stem it merely contained — `wurtzoxide` read as
"contains oxygen" purely because `oxide` appeared inside it.

## The authors' initialism

design/326 explicitly left the doped fractional case alone: "this is the case the
paper's own term dictionary must answer — the authors call it BSCF". A proposal is
accepted as an initialism when each of its letters is the first letter of a distinct
element, in the order the formula prints them. Oxygen is conventionally dropped, so
the initialism may be shorter than the element list.

## Where the name is claimed

`freeze(terms=...)` runs *after* the HTML parse, by which time
`Ba<sub>0.5</sub>` is already the words "barium zero point five" — so a key could
never match a real paper. Two things follow:

1. `build_term_dict` stores the survey's `rich` field as a key as well as `raw`,
   because `rich` is the printed form.
2. The match happens **before** the parse, marking the span, and the marks join
   `freeze`'s existing placeholder mapping afterwards. Longest key first, so
   `CoFe2O4` is not eaten by a shorter `Co` entry.

## The gate was too narrow, and real papers said so

The first version refused **11 of 23** proposals on one Adv. Mater. paper — and every
one of the 11 was a **correct name**, refused because my own table lacked the word:

```
NO  CeO2   -> ceria             unknown word
NO  MgO    -> magnesia          unknown word
NO  H2SO4  -> sulfuric acid     unknown word
NO  Pt2+   -> platinum two ion  unknown word
NO  C2H4   -> ethylene          unknown word
```

A 48% false-refusal rate would have left the feature inert. Three additions fixed it
without loosening what the gate is for:

1. **Trivial oxides by rule, not by list.** `ceria`, `magnesia`, `baria`, `yttria`
   follow one pattern — drop the trailing `a` and what remains starts an element's
   name. A list of these is always a journal behind.
2. **Acid and hydrocarbon names.** `acid` itself carries the hydrogen, so
   `sulfuric acid` accounts for H2SO4 exactly.
3. **Charge and structure words are not evidence.** `Pt2+` is "platinum two plus
   ion"; `Fe@SiO2` is "iron at silica". Those words say nothing about which elements
   are present, and refusing them threw away correct names.

Re-measured on the same paper: **27 of 28 accepted**, the one refusal being a name
that genuinely did not match. Wrong names are still refused — `cobalt oxide` for
`CoFe2O4`, `cobalt titanate` for `Co3O4`, `titanium nitride` for `TiO2`.

And the gate caught something nobody was looking for. ChemistryOpen prints `KCl`;
extraction produced `KCI` with a capital I. The proposed "potassium chloride" was
right and the **formula** was wrong, so the gate refused it — a corrupted extraction
surfaced by a speech check.

## Measured

| printed | without the dictionary | with it |
|---|---|---|
| `CoFe<sub>2</sub>O<sub>4</sub>` | C O F E 2 O 4 | **cobalt ferrite** |
| `Ba<sub>0.5</sub>Sr<sub>0.5</sub>Co<sub>0.8</sub>Fe<sub>0.2</sub>O<sub>3</sub>` | barium zero point five strontium zero point five cobalt … | **BSCF** |
| `BrO<sub>3</sub><sup>-</sup>` | B R O 3 to the minus | **bromate** to the minus |

## Locked

1. `term_dict.verify_term` gates every proposal; `build_term_dict` returns the
   accepted map and the refused printed forms.
2. The survey prompt asks for `spoken` per formula and says outright that a name
   leaving an element out will be discarded, and to leave it empty rather than guess.
3. `speak_terms_refused:N` and `speak_terms:N` reach the ingest warnings, because a
   name the gate threw out is a name the reader would otherwise have heard.
4. The dictionary lives on `PaperSession.speak_terms` — **per paper, never a module
   global** (design/337).
5. `paper_cache` **re-verifies on load**. A cache file can predate the gate or be
   hand-edited, so what comes back is checked again rather than trusted.
6. `/api/tts` and `/api/tts/spoken` accept an optional `cache_id`. Without it the
   reading is exactly what it was, so an older client keeps working.
7. The mobile client sends `cache_id` from reading playback, practice chunk audio,
   the miss-review word, and the spoken-form call — so the audio and the follow
   highlight agree.

**No `speak_norm` bump.** The MP3 cache key is derived from the spoken text itself,
so a paper that gains names gets new keys on its own, and a paper without them is
byte-identical to before. The three previous chips changed the reading for *every*
paper; this one changes nothing until a paper is ingested with names.

## Not this chip

- Re-ingesting existing papers to give them a dictionary. A paper keeps its current
  reading until it is ingested again.
- The web client does not send `cache_id` yet.
- Names for organic molecules, where the element-accounting gate is weak — a name
  like "acetic acid" accounts for C, H, O, but so would many wrong names.

## Test

`tests/test_design_343_term_dict.py` — formula parsing including case, doped
fractions, markup and unicode subscripts; anion stems carrying oxygen; composition
words ignored; an unknown word reported; seven correct names accepted; names that
drop, invent or leave a word unexplained refused; the authors' initialism accepted
and its wrong-order and foreign-letter variants refused; only verified rows reaching
the dictionary; the printed form stored as a key; the tagged formula and the
design/326 doped case end to end; nothing changing without a dictionary; longest key
winning; idempotence; and the cache re-verifying what it loads.
