// design/384 — the same sound missed twice in a row opens a sound drill;
// passing it, or using both tries, climbs back to the word.
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/practice_rhythm/miss_review.dart';

void main() {
  test('design/384 one miss does not open a sound drill', () {
    final lad = MissReviewLadder(soundN: 3, line: 0.60);

    expect(lad.afterWord(const [0.90, 0.11, 0.88]), isNull);
    expect(lad.drilling, isNull);
  });

  test('design/384 two misses of the same sound open that sound', () {
    final lad = MissReviewLadder(soundN: 3, line: 0.60);

    expect(lad.afterWord(const [0.90, 0.11, 0.88]), isNull);
    expect(lad.afterWord(const [0.91, 0.20, 0.87]), 1);
    expect(lad.drilling, 1);
  });

  test('design/384 a recovered sound does not carry its old streak', () {
    final lad = MissReviewLadder(soundN: 3, line: 0.60);

    expect(lad.afterWord(const [0.90, 0.11, 0.88]), isNull);
    expect(lad.afterWord(const [0.90, 0.80, 0.88]), isNull);
    expect(lad.afterWord(const [0.90, 0.11, 0.88]), isNull);
  });

  test('design/384 a row that does not line up never opens a drill', () {
    final lad = MissReviewLadder(soundN: 3, line: 0.60);

    expect(lad.afterWord(const [0.11, 0.11]), isNull);
    expect(lad.afterWord(const [0.11, 0.11]), isNull);
    expect(lad.drilling, isNull);
  });

  test('design/384 passing a sound drill climbs to the next waiting sound', () {
    final lad = MissReviewLadder(soundN: 3, line: 0.60);

    lad.afterWord(const [0.10, 0.10, 0.90]);
    expect(lad.afterWord(const [0.10, 0.10, 0.90]), 0);
    expect(lad.afterSound(0.80), 1);
    expect(lad.drilling, 1);
  });

  test('design/384 two failed sound tries climb back to the word', () {
    final lad = MissReviewLadder(soundN: 3, line: 0.60);

    lad.afterWord(const [0.90, 0.10, 0.90]);
    expect(lad.afterWord(const [0.90, 0.10, 0.90]), 1);
    expect(lad.afterSound(0.20), 1);
    expect(lad.afterSound(0.20), isNull);
    expect(lad.drilling, isNull);
  });

  test('design/384 a passed word is not this ladder\'s job', () {
    // The loop only calls afterWord on a miss. An empty ladder stays empty.
    final lad = MissReviewLadder(soundN: 2, line: 0.60);
    expect(lad.drilling, isNull);
    expect(lad.afterSound(0.99), isNull);
  });
}
