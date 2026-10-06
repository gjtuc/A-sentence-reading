// design/384 — a word's score cannot say which sound was missing, and that is
// the one thing a speaker about to re-read the word needs to know.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/practice_rhythm/word_phone_text.dart';
import 'package:sentence_reading/practice_skill/skill_score.dart';

const _weak = Color(0xFFFF0000);
const _strong = Color(0xFF000000);

List<Color?> _colorsOf(List<TextSpan> spans) =>
    [for (final s in spans) s.style?.color];

void main() {
  test('design/384 the per-sound row parses words barred and sounds spaced', () {
    final got = parseSlotSounds('95 88 11|76 80|-', slotN: 3);

    expect(got.length, 3);
    expect(got[0], [0.95, 0.88, 0.11]);
    expect(got[1], [0.76, 0.80]);
    // A word the model knows no sound for comes back empty, and the bar still
    // counted it, so the words stay lined up with the slots.
    expect(got[2], isEmpty);
  });

  test('design/384 a row that does not fit the slots is refused whole', () {
    expect(parseSlotSounds('95 88|76', slotN: 3), isEmpty);
    expect(parseSlotSounds('95 88|76', slotN: 1), isEmpty);
    expect(parseSlotSounds('95 101|76', slotN: 2), isEmpty);
    expect(parseSlotSounds('95 x|76', slotN: 2), isEmpty);
    expect(parseSlotSounds('', slotN: 2), isEmpty);
  });

  test('design/384 the sounds under the line are the ones picked out', () {
    final spans = reviewSoundSpans(
      phone: 'p r ɪ p ɛ ɹ d',
      sounds: const [0.95, 0.88, 0.91, 0.93, 0.11, 0.34, 0.90],
      line: 0.60,
      weak: _weak,
      strong: _strong,
    );

    // Seven symbols and six gaps between them.
    expect(spans.length, 13);
    expect(spans[0].text, 'p');
    expect(spans[8].text, 'ɛ');
    expect(spans[8].style?.color, _weak);
    expect(spans[10].text, 'ɹ');
    expect(spans[10].style?.color, _weak);
    expect(spans[12].text, 'd');
    expect(spans[12].style?.color, _strong);
  });

  test('design/384 nothing is painted when the two sides do not line up', () {
    // A symbol the model's vocabulary does not carry is dropped before scoring.
    // Painting through that gap would mark the wrong symbol.
    final spans = reviewSoundSpans(
      phone: 'p r ɪ p ɛ ɹ d',
      sounds: const [0.95, 0.11],
      line: 0.60,
      weak: _weak,
      strong: _strong,
    );

    expect(spans.length, 1);
    expect(spans.single.text, 'p r ɪ p ɛ ɹ d');
    expect(spans.single.style?.color, _strong);
    expect(_colorsOf(spans), isNot(contains(_weak)));
  });

  test('design/384 an empty word paints nothing red', () {
    final spans = reviewSoundSpans(
      phone: '   ',
      sounds: const [],
      line: 0.60,
      weak: _weak,
      strong: _strong,
    );

    expect(spans.single.text, '');
  });

  test('design/384 the symbols are counted the way the server split them', () {
    // The ask goes out whitespace-separated and the server does a plain split.
    expect(phoneSymbols('p r ɪ p ɛ ɹ d').length, 7);
    expect(phoneSymbols('  eɪ   t  ').length, 2);
    expect(phoneSymbols(''), isEmpty);
  });

  test('design/393 a focus paints that one sound only', () {
    final spans = reviewSoundSpans(
      phone: 'p r ɪ p ɛ ɹ d',
      sounds: const [0.95, 0.88, 0.91, 0.93, 0.11, 0.34, 0.90],
      line: 0.60,
      weak: _weak,
      strong: _strong,
      focus: 4,
    );

    expect(spans[8].text, 'ɛ');
    expect(spans[8].style?.color, _weak);
    // ɹ is under the line too, but it is not the one aimed at.
    expect(spans[10].text, 'ɹ');
    expect(spans[10].style?.color, _strong);
    expect(_colorsOf(spans).where((c) => c == _weak).length, 1);
  });

  test('design/393 a focus of -1 paints none', () {
    final spans = reviewSoundSpans(
      phone: 'p r ɪ',
      sounds: const [0.10, 0.11, 0.12],
      line: 0.60,
      weak: _weak,
      strong: _strong,
      focus: -1,
    );
    expect(_colorsOf(spans), isNot(contains(_weak)));
  });
}
