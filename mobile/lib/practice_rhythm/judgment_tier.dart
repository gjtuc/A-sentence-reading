/// design/214 — accuracy → judgment tier (same bands as skill adapt 212).
library;

enum JudgmentTier { good, great, perfect }

/// [accuracy] is 0..1 coverage from content-word scoring.
JudgmentTier judgmentTierFor(double accuracy) {
  if (accuracy < 0.60) return JudgmentTier.good;
  if (accuracy < 0.75) return JudgmentTier.great;
  return JudgmentTier.perfect;
}

String judgmentTierKey(JudgmentTier tier) {
  switch (tier) {
    case JudgmentTier.good:
      return 'good';
    case JudgmentTier.great:
      return 'great';
    case JudgmentTier.perfect:
      return 'perfect';
  }
}
