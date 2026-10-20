# 433 — Letters the PDF never named, and its own sub/superscripts

## Ask

The paper prints `0.25 mgPt cm−2` with `Pt` lowered and `−2` raised; the app showed
the sentence flat, and the minus was missing. Fix it so that every new font does not
need a new table entry.

## Why the minus had no information

A PDF character has two parts: the shape the font draws, and (separately, in the
ToUnicode map) the Unicode character the shape stands for. Some fonts leave the second
part out. The shape still prints, but extraction gets a control code, private-use code
or U+FFFD. `get_text("words")` treats a control code as a space, so `cm−2` reached the
sentences as `cm 2`.

## Measured

Over the PDFs on this PC (344 files, 198 papers):

| | |
|---|---|
| papers with unnamed characters | 110 |
| distinct (font, glyph id) shapes | 467, in 69 fonts |
| shapes that occur in one paper only | 89% |
| characters named by the font's own glyph names | 6% |

On 47 hand-labelled shapes: the layout service read 13 correctly, shape matching
against system fonts 25 (33 in its top three), Gemini vision on numbered sheets of 12
crops 38. Gemini's misses were mostly the length of a dash and `fi`/`fl` read as `f`.

`C<number>` glyph names (Elsevier `AdvPS_*`) are not character codes: in one whole-text
font `g` is `C33`, `w` is `C48`. They are named like any other shape.

## Change

`pdf/drawn_glyphs.py`:

- Words are built from `rawdict` glyphs with the flags `get_text("words")` uses. On 636
  pages of 79 PDFs the words equal MuPDF's on 626; the other 10 are three files with a
  zero-width space, a combining overlay or a right-to-left character. The built words
  are used only when the paper has unnamed glyphs that were named.
- Each unnamed shape is named once per paper, keyed by (font, glyph id): the font's glyph
  name through the Adobe Glyph List first, then one Gemini vision call per sheet of up
  to 12 shapes (at most 120 shapes; the sheets run together). The crop shown is the
  shape's largest occurrence. A dash takes its kind from where the glyph is used: inside
  a script or signing a number it is a minus, between digits an en dash.
- The work starts in the background when the layout service is called
  (`vision_ocr.recover_pdf_text`), and the boxes wait for that run instead of repeating
  it. Results are cached by file content.
- Sub/superscripts come from geometry: a glyph smaller than 0.85 of its line's text
  size whose baseline moves more than 0.06 of its full-size neighbour's size. The
  neighbour, not the line, is the reference, because a table row can hold two baselines.
- `script_forms` lists the words the paper prints with scripts (`mgPt` →
  `mg<sub>Pt</sub>`). A form is kept when 80% of the paper's occurrences agree on where
  the markup sits, and only when the word also has unscripted letters, so a lone
  superscript `12` never marks every `12`. A raised `o` before `C` or `F` becomes `°`.
- After the sentences are made, `app.py` gives each word the paper's form
  (`apply_script_forms`). Words in `<i>`/`<em>` are left alone.

The reader's faded neighbour sentences (design/414) render the same sub/superscripts
(`annotationRichSpansForSentence`).

On the paper that raised this, the sentence now reads, from the PDF alone:
`0.25 mg<sub>Pt</sub> cm<sup>−2</sup> and 0.3 mg<sub>Pt</sub> cm<sup>−2</sup> … 5
cm<sup>2</sup> … 200 ml min<sup>−1</sup> of pure O<sub>2</sub>`. Five shapes were
named in one call, 41 forms found.

`PIPELINE_VERSION` is `rich-v26`. `fonttools` is a server dependency.

## Signals

Ingest warnings: `drawn_glyph_unnamed_glyphs`, `drawn_glyph_unnamed_chars`,
`drawn_glyph_named_by_font`, `drawn_glyph_named_by_vision`, `drawn_glyph_unresolved`,
`drawn_glyph_vision_calls`, `drawn_glyph_vision_failed`, `drawn_glyph_vision_skipped`,
`script_forms`, `script_forms_applied`.

`ASR_GLYPH_VISION=0` turns the vision call off; the suite runs with it off.

## Not covered

- A font whose map is present but wrong (`µl` printed, `ll` extracted) is not an
  unnamed glyph and is not touched.
- A script printed on its own line by MuPDF is measured against that line and missed.
