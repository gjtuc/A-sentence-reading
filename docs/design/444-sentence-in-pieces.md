# 444 — A long sentence shown in its pieces (trial switch)

## Ask

Wider line spacing than 아주 넓게 (2.2) was asked about for long paper sentences. The
research does not support it for most readers: reading speed stops improving at about
1.2–1.5 times the font size, and wider lines read as separate fragments and push a long
sentence past the pane. What makes a long sentence hard is that its shape is hidden: it
wraps wherever the width ran out (`the synthesis of / monodisperse`, `(Table / S1`).
The reader chose to break the sentence where a reader would pause instead.

## Change

Settings → 읽기 화면 (phone) and 웹 읽기 화면 (web) gain one shared switch,
`긴 문장 끊어 보기 (시험)`, off by default (`reading_clause_breaks_v1`).

When on, `clauseBreakOffsets` (`mobile/lib/api/clause_breaks.dart`) picks spaces in a
sentence of at least 120 characters:

- after a comma followed by a clause word (which, where, whereas, while, although,
  though, because, but, including, such, thereby, and participles such as resulting,
  indicating, suggesting, demonstrating, revealing, confirming, enabling, yielding);
- after a semicolon;
- before each mark of a numbered list `(i) (ii) (iii)`, `(a) (b) (c)` or `(1) (2)` that
  counts up from one. Two marks with no comma between them, `shown in (a) and (b)`, is
  how a paper points at panels, so that takes three marks or a comma.

Nothing breaks inside brackets. A break that would leave a piece under 25 characters or
a tail under 15 is dropped, so `including (i)` stays on one line.

Each chosen space is drawn as a line break. Both are one character, so highlight offsets
on the plain text (design/166, 182) do not move, and the paint path finds the same word
under the finger. `buildAnnotatedSpans` does it in both of its paths: on the plain text
when there are highlights, and on the markup otherwise, so italics and sub/superscripts
stay (`richWithClauseBreaks` walks the tags and folded spaces the way
`plainFromRichHtml` does). The sentence text, the translation and the scoring are
untouched.

On the Advanced Materials Pt–Co paper, 35 of 121 sentences over 120 characters break,
into 85 pieces.

Files: `mobile/lib/api/clause_breaks.dart`, `mobile/lib/api/rich_sentence.dart`,
`mobile/lib/widgets/annotated_sentence_text.dart`, `mobile/lib/state/web_reading_prefs.dart`,
`mobile/lib/screens/reader_screen.dart`, `mobile/lib/screens/settings_screen.dart`,
`mobile/test/clause_breaks_test.dart`, `mobile/test/reader_screen_widget_test.dart`.
