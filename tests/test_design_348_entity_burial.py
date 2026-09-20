"""design/348 — the voice read the escape, not the character.

A ChemistryOpen sentence reached the reader as

    ranging from 600 to 1700&amp;amp;amp;deg;C, FP was contaminant-free

and the practice voice said the entity out loud. Three faults stacked:

1. `sanitize_sentence_html` was **not idempotent**. A sentence with no tag took a fast
   path that escaped `&` without first decoding what was already an entity, so every
   pass buried the text one `&amp;` deeper: `&lt;` then `&amp;lt;` then `&amp;amp;lt;`.
   The tagged path was already safe, because `convert_charrefs` decodes first.
2. `plain_text` never decoded at all, so the voice and the coverage ruler both received
   `&lt;600&deg;C` verbatim.
3. The speech rules peel one level, which is enough for `&deg;` but not for text that
   has been through the sanitiser three times.

Measured across the stored traces: 354 entities in the sentences, `&amp;` 176 times,
`&gt;` 121, `&lt;` 57 — and `ChemistryOpen` alone carried 55.
"""

from __future__ import annotations

from sentence_reading.llm.richtext import plain_text, sanitize_sentence_html, unescape_fully
from sentence_reading.llm.tts_speak import spoken_text_for_tts


# ------------------------------------------------- the sentence that showed it


def test_the_chemistryopen_sentence_is_spoken_as_a_temperature() -> None:
    buried = "ranging from 600 to 1700&amp;amp;amp;deg;C, FP was contaminant-free."
    said = spoken_text_for_tts(plain_text(buried))
    assert "degrees celsius" in said.lower()
    assert "&" not in said
    assert "deg;" not in said


def test_a_single_level_entity_still_works() -> None:
    said = spoken_text_for_tts(plain_text("at temperature of &lt;600&deg;C the film held."))
    assert "less than 600 degrees celsius" in said.lower()


def test_a_buried_comparison_is_spoken() -> None:
    said = spoken_text_for_tts(plain_text("The ratio was &amp;gt; 87% after 3000 cycles."))
    assert "greater than" in said.lower()
    assert "&" not in said


# ------------------------------------------------- the fault itself


def test_sanitize_is_idempotent() -> None:
    """The burial mechanism: each pass added a level to a sentence with no tag."""
    for s in (
        "at temperature of &lt;600&deg;C the film held.",
        "The ratio was &gt; 87% after 3000 cycles.",
        "Milli-Q water (&gt; 18 MOhm cm at 25 C) was used throughout.",
    ):
        once = sanitize_sentence_html(s)
        assert sanitize_sentence_html(once) == once, s
        assert sanitize_sentence_html(sanitize_sentence_html(once)) == once, s


def test_sanitize_is_idempotent_with_tags_too() -> None:
    s = "CO<sub>2</sub> + H<sub>2</sub> &gt; CO + H<sub>2</sub>O was measured."
    once = sanitize_sentence_html(s)
    assert sanitize_sentence_html(once) == once
    assert "<sub>" in once


def test_plain_text_returns_characters_not_escapes() -> None:
    assert plain_text("at &lt;600&deg;C today") == "at <600\u00b0C today"
    assert plain_text("CO<sub>2</sub> &gt; CO here") == "CO2 > CO here"


def test_unescape_stops_when_it_stops_changing() -> None:
    assert unescape_fully("plain text") == "plain text"
    assert unescape_fully("&amp;amp;amp;deg;") == "\u00b0"


# ------------------------------------------------- what must not change


def test_display_html_still_escapes_for_safety() -> None:
    """Decoding happens *before* escaping, so the stored HTML is still safe."""
    out = sanitize_sentence_html("at &lt;600 &amp; rising")
    assert "&lt;" in out
    assert "<600" not in out


def test_a_script_tag_does_not_survive_decoding() -> None:
    out = sanitize_sentence_html("&lt;script&gt;alert(1)&lt;/script&gt; and prose here")
    assert "<script" not in out.lower()
    assert "prose here" in out


def test_allowed_tags_are_untouched() -> None:
    s = "The e<sub>g</sub> filling and <i>\u03c3</i> were measured."
    assert sanitize_sentence_html(s) == s
