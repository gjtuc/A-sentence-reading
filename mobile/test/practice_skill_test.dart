import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/practice_skill/chunk_density.dart';
import 'package:sentence_reading/practice_skill/skill_adapt.dart';
import 'package:sentence_reading/practice_skill/skill_score.dart';
import 'package:sentence_reading/practice_skill/skill_store.dart';

void main() {
  test('content word coverage ignores order and insertions', () {
    final r = contentWordCoverage(
      'catalyst prepared carefully',
      'carefully prepared catalyst noise words',
    );
    expect(r.ok, isTrue);
    expect(r.accuracy, greaterThanOrEqualTo(0.99));
  });

  test('empty content ref unscored', () {
    final r = contentWordCoverage('the a of', 'hello');
    expect(r.ok, isFalse);
    expect(r.error, 'empty_content_ref');
  });

  test('effectiveChunks finer inserts mid prefix', () {
    final base = [
      'The catalyst',
      'The catalyst was prepared by reduction',
    ];
    final out = effectiveChunks(base, 1);
    expect(out.length, greaterThan(base.length));
    expect(out.last, base.last);
  });

  test('adapt finer when avg low and can finer', () {
    final state = SkillState(blockSum: 0.5, blockN: 5, density: 0, tier: 2);
    final d = decideSkillAdapt(
      state: state,
      baseChunks: [
        'The catalyst',
        'The catalyst was prepared by reduction of the oxide',
      ],
    );
    expect(d.densityDelta, 1);
  });
}
