// design/385 — warming walks from the sentence about to be read.
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/practice_skill/sound_warm_order.dart';

void main() {
  test('design/385 practice cursor wins when it is on the paper', () {
    expect(
      soundWarmStart(readerIndex: 2, practiceIndex: 40, sentenceN: 168),
      40,
    );
  });

  test('design/385 a practice index off the paper falls back to the reader', () {
    expect(
      soundWarmStart(readerIndex: 12, practiceIndex: 200, sentenceN: 168),
      12,
    );
    expect(
      soundWarmStart(readerIndex: 12, practiceIndex: -1, sentenceN: 168),
      12,
    );
  });

  test('design/385 no practice row uses the reader cursor', () {
    expect(
      soundWarmStart(readerIndex: 7, practiceIndex: null, sentenceN: 20),
      7,
    );
  });

  test('design/385 both cursors off the paper start at zero', () {
    expect(
      soundWarmStart(readerIndex: 99, practiceIndex: 99, sentenceN: 10),
      0,
    );
  });

  test('design/385 rotate puts the cursor sentence first and wraps', () {
    expect(
      soundWarmTexts(['one', 'two', 'three', 'four'], from: 2),
      ['three', 'four', 'one', 'two'],
    );
  });

  test('design/385 blanks drop after the rotate so the cursor stays put', () {
    expect(
      soundWarmTexts(['one', '', 'three', 'four'], from: 1),
      ['three', 'four', 'one'],
    );
  });

  test('design/385 an out of range from walks from the start', () {
    expect(soundWarmTexts(['a', 'b', 'c'], from: -1), ['a', 'b', 'c']);
    expect(soundWarmTexts(['a', 'b', 'c'], from: 9), ['a', 'b', 'c']);
  });

  test('design/385 empty paper sends nothing', () {
    expect(soundWarmTexts(const []), isEmpty);
  });
}
