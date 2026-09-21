# 356 — Six author headshots were six figures

**Version:** 0.3.352 · Status: **locked**  
Extends [338](338-panel-pairing-and-page-graphics.md)

## Why

`slot_census` reported `body_without_caption_n: 13` on `d4cs00527a`, and a count is not a
cause. Opening all thirteen named every one:

| n | what they are |
|---|---|
| 6 | **author headshots**, 114–115 × 141–143 pt, each printed beside a biography |
| 6 | front-page furniture: a cover graphic over **58% of page 1**, the journal banner, the `View Article Online` badge on two pages, a logo beside `Cite this:` |
| 1 | a 424 × 124 box in body text on page 7, which may be a real figure |

Every one became its own carousel entry labelled `번호 없는 그림`. Studying that paper meant
swiping through six portraits of its authors.

design/338's `demote_repeating_bodies` misses them. It clusters on the **whole rect**,
because a journal logo repeats at the same coordinates on every page — and these six sit at
six different positions, two per column across two pages. Their signature is the **size**:
within one or two points of each other, six times over.

## Locked

`demote_same_size_unclaimed` groups the bodies **no caption claimed** by width and height
within design/338's 4-point tolerance, and re-types a group of **3 or more spanning 2 or
more pages** as chrome.

Both bounds carry their own reason:

- **3 members**, because two is a coincidence a real paper can produce — the
  `View Article Online` badge appears exactly twice, and it needs its own evidence rather
  than this rule.
- **2 pages**, because four equal panels of one figure on one page look exactly like this.

And it runs **after caption pairing**, so every figure the paper captioned is already spoken
for and out of reach. That is the property that makes the rule safe rather than the
thresholds.

| paper | `body_without_caption_n` | `filled_n` |
|---|---|---|
| `d4cs00527a` | **13 → 7** | 27 → **27** |
| `cs5b00357` | 4 → 4 | 14 → 14 |
| `srep41797` | 0 → 0 | 10 → 10 |

`filled_n` unchanged is the check that matters: no captioned figure moved. Reported as
`same_size_chrome_n`, which is 6 on the review and 0 elsewhere.

## The 7 that remain, named

Not fixed, but no longer unidentified:

- **6 front-page furniture.** The strongest signal is position, not size: a body above the
  paper's own title on page 1 is the journal's, and `fig:30` covers 58% of that page. That
  needs the title box's rectangle, which this chip does not reach for.
- **1 possible figure** on page 7. Its neighbouring text below is the copyright footer, so
  an "adjacent text is apparatus" rule would demote it — which is why that rule was not
  written. It may be a scheme whose caption Azure missed.

## Not this chip

- Front-page furniture, which wants the title's position
- The `View Article Online` badge pair
- `cs5b00357`'s 4, which are unique sizes and need their own look

## Test

`tests/test_design_356_same_size_is_furniture.py` — six same-size bodies demoted and kept
out of the carousel, a four-panel figure on one page left alone, two of a size left alone,
different sizes left alone, a captioned figure out of reach, tables using their own kind,
and both bounds pinned to the reasons above.
