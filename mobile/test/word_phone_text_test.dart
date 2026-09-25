import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/practice_rhythm/follow_span.dart';
import 'package:sentence_reading/practice_rhythm/word_phone_text.dart';

void main() {
  test('each half of a hyphenated word keeps its own phones', () {
    const text = 'fuel-cell electrodes';
    final words = wordPhonesFor(
      text: text,
      spans: const [
        FollowSpan(start: 0, end: 4, weight: 4, phone: 'f j uː l'),
        FollowSpan(start: 5, end: 9, weight: 4, phone: 's ɛ l'),
        FollowSpan(start: 10, end: 20, weight: 10, phone: 'ɪ l ɛ k t ɹ oʊ d z'),
      ],
    );
    expect(words.map((w) => w.word).toList(), ['fuel-', 'cell', 'electrodes']);
    expect(words[0].phone, 'f j uː l');
    expect(words[1].phone, 's ɛ l');
    expect(words[2].phone, 'ɪ l ɛ k t ɹ oʊ d z');
  });

  test('a plain word is one column', () {
    final words = wordPhonesFor(
      text: 'Chemical vapor',
      spans: const [
        FollowSpan(start: 0, end: 8, weight: 8, phone: 'k ɛ m ɪ k əl'),
        FollowSpan(start: 9, end: 14, weight: 5, phone: 'v eɪ p ɚ'),
      ],
    );
    expect(words, hasLength(2));
    expect(words.first.word, 'Chemical');
  });

  test('a dangling hyphen does not split', () {
    final words = wordPhonesFor(text: 'end- -start', spans: const []);
    expect(words.map((w) => w.word).toList(), ['end-', '-start']);
  });
}
