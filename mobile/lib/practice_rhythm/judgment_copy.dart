/// design/214 — English judgment copy pools + last-avoid pick.
library;

import 'dart:math';

import 'judgment_tier.dart';

const List<String> kJudgmentCopyGood = [
  'Nice try!',
  'Keep going!',
  'Almost there!',
  'Solid!',
  'You got this!',
];

const List<String> kJudgmentCopyGreat = [
  'Nice!',
  'Looking good!',
  'You got it!',
  'Clean!',
  'Smooth!',
];

const List<String> kJudgmentCopyPerfect = [
  'Nailed it!',
  'Fire!',
  'Crushing it!',
  'Perfect!',
  'On point!',
  'Boom!',
];

List<String> judgmentCopyPool(JudgmentTier tier) {
  switch (tier) {
    case JudgmentTier.good:
      return kJudgmentCopyGood;
    case JudgmentTier.great:
      return kJudgmentCopyGreat;
    case JudgmentTier.perfect:
      return kJudgmentCopyPerfect;
  }
}

/// Prefer a line different from [lastCopy] when the pool has 2+.
String pickJudgmentCopy(
  JudgmentTier tier, {
  String? lastCopy,
  Random? random,
}) {
  final pool = judgmentCopyPool(tier);
  if (pool.isEmpty) return 'Nice!';
  if (pool.length == 1) return pool.first;
  final rng = random ?? Random();
  final candidates =
      lastCopy == null ? pool : pool.where((s) => s != lastCopy).toList();
  final use = candidates.isEmpty ? pool : candidates;
  return use[rng.nextInt(use.length)];
}
