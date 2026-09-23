import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/practice_rhythm/follow_span.dart';
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

  test('epoch wait until target block means', () {
    final state = SkillState(
      epochMeans: const [0.5, 0.5, 0.5],
      epochTargetN: 5,
      density: 0,
      tier: 2,
    );
    final d = decideSkillAdapt(
      state: state,
      baseChunks: [
        'The catalyst',
        'The catalyst was prepared by reduction of the oxide',
      ],
    );
    expect(d.reason, 'epoch_wait');
    expect(d.densityDelta, 0);
  });

  test('epoch finer when avg <= 80 and can finer', () {
    final state = SkillState(
      epochMeans: const [0.7, 0.7, 0.7, 0.7, 0.7],
      epochTargetN: 5,
      density: 0,
      tier: 2,
    );
    final d = decideSkillAdapt(
      state: state,
      baseChunks: [
        'The catalyst',
        'The catalyst was prepared by reduction of the oxide',
      ],
    );
    expect(d.densityDelta, 1);
    expect(d.reason, 'finer');
  });

  test('epoch coarser when avg >= 90', () {
    final state = SkillState(
      epochMeans: const [0.95, 0.92, 0.91, 0.90, 0.93],
      epochTargetN: 5,
      density: 1,
      tier: 2,
    );
    final d = decideSkillAdapt(
      state: state,
      baseChunks: [
        'The catalyst',
        'The catalyst was prepared by reduction of the oxide',
      ],
    );
    expect(d.densityDelta, -1);
    expect(d.reason, 'coarser');
  });

  test('epoch hold in 80-90 band', () {
    final state = SkillState(
      epochMeans: const [0.85, 0.85, 0.85, 0.85, 0.85],
      epochTargetN: 5,
      density: 0,
      tier: 2,
    );
    final d = decideSkillAdapt(
      state: state,
      baseChunks: [
        'The catalyst',
        'The catalyst was prepared by reduction of the oxide',
      ],
    );
    expect(d.reason, 'hold');
    expect(d.densityDelta, 0);
  });

  test('rollSkillEpochTarget in 5..10', () {
    for (var i = 0; i < 40; i++) {
      final n = rollSkillEpochTarget();
      expect(n, inInclusiveRange(5, 10));
    }
  });

  test('a printed word is one slot even when spoken as letters', () {
    const display = 'CVD is a technique for semiconductor.';
    const spoken = 'c v d is a technique for semiconductor.';
    final spans = [
      const FollowSpan(start: 0, end: 3, weight: 5),
      FollowSpan(
        start: display.indexOf('is'),
        end: display.indexOf('is') + 2,
        weight: 2,
      ),
      FollowSpan(
        start: display.indexOf('a '),
        end: display.indexOf('a ') + 1,
        weight: 1,
      ),
      FollowSpan(
        start: display.indexOf('technique'),
        end: display.indexOf('technique') + 'technique'.length,
        weight: 'technique'.length,
      ),
      FollowSpan(
        start: display.indexOf('for'),
        end: display.indexOf('for') + 3,
        weight: 3,
      ),
      FollowSpan(
        start: display.indexOf('semiconductor'),
        end: display.indexOf('semiconductor') + 'semiconductor'.length,
        weight: 'semiconductor'.length,
      ),
    ];
    final missedC = spokenSlotCoverage(
      display: display,
      spoken: spoken,
      spans: spans,
      heard: 'v d is a technique for semiconductor',
    );
    expect(missedC.ok, isTrue);
    expect(missedC.refN, 6);
    expect(missedC.hitN, 5);
    expect(missedC.accuracy, closeTo(5 / 6, 0.0001));
    expect(missedC.missedSpans, hasLength(1));
    expect(missedC.missedSpans.single.start, 0);
    expect(missedC.missedSpans.single.end, 3);

    final all = spokenSlotCoverage(
      display: display,
      spoken: spoken,
      spans: spans,
      heard: spoken,
    );
    expect(all.hitN, 6);
    expect(all.missedSpans, isEmpty);
  });

  test('a renamed symbol lights the printed token', () {
    const display = 'Pt particle is a hard';
    const spoken = 'platinum particle is a hard';
    final spans = [
      const FollowSpan(start: 0, end: 2, weight: 8),
      FollowSpan(
        start: display.indexOf('particle'),
        end: display.indexOf('particle') + 'particle'.length,
        weight: 'particle'.length,
      ),
      FollowSpan(
        start: display.indexOf('is'),
        end: display.indexOf('is') + 2,
        weight: 2,
      ),
      FollowSpan(
        start: display.indexOf('a '),
        end: display.indexOf('a ') + 1,
        weight: 1,
      ),
      FollowSpan(
        start: display.indexOf('hard'),
        end: display.indexOf('hard') + 4,
        weight: 4,
      ),
    ];
    final missed = spokenSlotCoverage(
      display: display,
      spoken: spoken,
      spans: spans,
      heard: 'particle is a hard',
    );
    expect(missed.refN, 5);
    expect(missed.hitN, 4);
    expect(display.substring(missed.missedSpans.single.start, missed.missedSpans.single.end), 'Pt');
  });

  test('replay misses include function words from the spoken slots', () {
    const display = 'The catalyst is stable';
    const spoken = 'The catalyst is stable';
    final spans = [
      const FollowSpan(start: 0, end: 3, weight: 3),
      FollowSpan(
        start: display.indexOf('catalyst'),
        end: display.indexOf('catalyst') + 8,
        weight: 8,
      ),
      FollowSpan(
        start: display.indexOf('is'),
        end: display.indexOf('is') + 2,
        weight: 2,
      ),
      FollowSpan(
        start: display.indexOf('stable'),
        end: display.indexOf('stable') + 6,
        weight: 6,
      ),
    ];
    final missed = spokenSlotCoverage(
      display: display,
      spoken: spoken,
      spans: spans,
      heard: 'stable',
    );
    expect(missed.missedSpans, hasLength(3));
    expect(missed.hitN, 1);
    expect(missed.refN, 4);
  });

  test('empty pairing reports the walk step that failed', () {
    final none = diagnoseSpokenSlots(
      display: 'Alpha beta',
      spoken: 'alpha beta',
      spans: const [],
      heard: 'alpha',
    );
    expect(none.slotCode, 'no_spans');
    expect(none.score.ok, isFalse);
    expect(none.score.error, 'no_spans');
    expect(none.spanN, 0);

    final zero = diagnoseSpokenSlots(
      display: 'Alpha beta',
      spoken: 'alpha beta',
      spans: const [FollowSpan(start: 0, end: 5, weight: 0)],
      heard: 'alpha',
    );
    expect(zero.slotCode, 'weight_zero');
    expect(zero.posSpanN, 0);

    final past = diagnoseSpokenSlots(
      display: 'Alpha',
      spoken: 'alpha',
      spans: const [FollowSpan(start: 0, end: 5, weight: 40)],
      heard: 'alpha',
    );
    expect(past.slotCode, 'walk_past_end');
    expect(past.walkI, 0);
    expect(past.pieceWeight, 40);
    expect(past.remain, 5);
    expect(past.score.error, 'walk_past_end');

    final outOfRange = diagnoseSpokenSlots(
      display: 'Alpha',
      spoken: 'alpha',
      spans: const [FollowSpan(start: 0, end: 99, weight: 5)],
      heard: 'alpha',
    );
    expect(outOfRange.slotCode, 'span_out_of_range');
    expect(outOfRange.posSpanN, 1);
  });

  test('words before a broken pairing still score', () {
    const display = 'Alpha beta gamma';
    final scored = diagnoseSpokenSlots(
      display: display,
      spoken: 'alpha beta GAMMA leftover',
      spans: const [
        FollowSpan(start: 0, end: 5, weight: 5),
        FollowSpan(start: 6, end: 10, weight: 4),
        FollowSpan(start: 0, end: 0, weight: 16),
      ],
      heard: 'alpha beta',
    );
    expect(scored.slotCode, 'ok');
    expect(scored.score.ok, isTrue);
    expect(scored.score.refN, 2);
    expect(scored.score.hitN, 2);
    expect(scored.posSpanN, 2);
  });
}
