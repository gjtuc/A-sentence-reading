import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/practice_rhythm/follow_span.dart';
import 'package:sentence_reading/practice_rhythm/judgment_copy.dart';
import 'package:sentence_reading/practice_rhythm/judgment_tier.dart';

void main() {
  test('judgment tiers match adapt bands', () {
    expect(judgmentTierFor(0.0), JudgmentTier.good);
    expect(judgmentTierFor(0.5999), JudgmentTier.good);
    expect(judgmentTierFor(0.60), JudgmentTier.great);
    expect(judgmentTierFor(0.7499), JudgmentTier.great);
    expect(judgmentTierFor(0.75), JudgmentTier.perfect);
    expect(judgmentTierFor(1.0), JudgmentTier.perfect);
  });

  test('judgment tier keys are evidence-safe', () {
    expect(judgmentTierKey(JudgmentTier.good), 'good');
    expect(judgmentTierKey(JudgmentTier.great), 'great');
    expect(judgmentTierKey(JudgmentTier.perfect), 'perfect');
  });

  test('pickJudgmentCopy avoids last when possible', () {
    final rng = Random(7);
    final first = pickJudgmentCopy(JudgmentTier.perfect, random: rng);
    final second = pickJudgmentCopy(
      JudgmentTier.perfect,
      lastCopy: first,
      random: rng,
    );
    expect(second, isNot(equals(first)));
    expect(kJudgmentCopyPerfect.contains(second), isTrue);
  });

  test('follow light uses media weight and skips dropped spans', () {
    final spans = [
      const FollowSpan(start: 0, end: 3, weight: 0),
      const FollowSpan(start: 4, end: 7, weight: 10),
      const FollowSpan(start: 8, end: 11, weight: 10),
    ];
    expect(activeFollowSpan(spans, 0, 0), isNull);
    expect(activeFollowSpan(const [], 10, 100), isNull);
    final early = activeFollowSpan(spans, 0, 1000);
    expect(early?.start, 4);
    final late = activeFollowSpan(spans, 999, 1000);
    expect(late?.start, 8);
    expect(activeFollowSpan(spans, 1000, 1000)?.end, 11);
  });
}
