# 348 — The voice read the escape, not the character

**Version:** 0.3.344 · Status: **locked**  
Found while measuring [347](347-the-ruler-was-wrong-more-often-than-the-pipeline.md)

## Why

A ChemistryOpen sentence reached the reader as

```
ranging from 600 to 1700&amp;amp;amp;deg;C, FP was contaminant-free
```

and the practice voice said the entity out loud. Across the stored traces the sentences
carry **354** HTML entities: `&amp;` 176 times, `&gt;` 121, `&lt;` 57. One paper alone
carried 55.

Three faults stacked, and only the third was visible.

**`sanitize_sentence_html` was not idempotent.** A sentence with no tag took a fast path
that escaped `&` without first decoding what was already an entity, so every pass buried
the text one level deeper:

```
&lt;   →   &amp;lt;   →   &amp;amp;lt;   →   …
```

The tagged path was already safe — `HTMLParser(convert_charrefs=True)` decodes before
`handle_data` re-escapes, which round-trips exactly. Only the shortcut was wrong, and
that is why the defect looked random: it depended on whether the sentence happened to
carry a `<sub>`.

**`plain_text` never decoded at all.** It is what feeds the voice and the coverage
ruler, and it returned `&lt;600&deg;C` verbatim.

**The speech rules peel one level.** Enough for `&deg;`, not for text that has been
through the sanitiser three times, so `1700&amp;amp;amp;deg;C` was spoken as
`1700&deg;C` — the entity read aloud.

## Locked

`unescape_fully` peels until the text stops changing, bounded at six passes so a
hostile `&amp;amp;…` chain cannot loop.

- `sanitize_sentence_html` decodes before escaping on **both** paths, which makes it
  idempotent. Escaping still happens, so the stored HTML is as safe as before:
  `&lt;script&gt;` decodes to a tag and is then stripped by the allow-list, which is a
  better outcome than displaying it as text.
- `plain_text` decodes on both paths, so the voice receives `<` and `°` as characters.

Because the repair happens at read time, sentences already stored with buried entities
speak correctly without being ingested again.

| stored | spoken before | spoken now |
|---|---|---|
| `1700&amp;amp;amp;deg;C` | `1700&deg;C` | `1700 degrees Celsius` |
| `&amp;gt; 87%` | `&gt; 87%` | `greater than 87%` |
| `&lt;600&deg;C` | already worked | unchanged |

## Not this chip

A reaction arrow written `>` is spoken as *greater than*:
`CO<sub>2</sub> + H<sub>2</sub> &gt; CO + H<sub>2</sub>O` becomes *carbon dioxide plus
hydrogen greater than carbon monoxide plus water*. The source really does print `>`, so
telling an arrow from a comparison needs its own evidence.

## Test

`tests/test_design_348_entity_burial.py` — the ChemistryOpen sentence spoken as a
temperature, single-level entities still working, a buried comparison spoken,
idempotence with and without tags, `plain_text` returning characters, the peel stopping
when it stops changing, display HTML still escaped, a script tag not surviving the
decode, and the allowed tags untouched.
