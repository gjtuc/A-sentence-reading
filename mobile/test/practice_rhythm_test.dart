import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
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
}
