/// design/212+215 — adapt density / tier from epoch of focus-block means.
library;

import 'dart:math';

import 'chunk_density.dart';
import 'skill_store.dart';

const int kSkillEpochMinN = 5;
const int kSkillEpochMaxN = 10;
const double kSkillFinerThreshold = 0.80;
const double kSkillCoarserThreshold = 0.90;

int rollSkillEpochTarget([Random? random]) {
  final rng = random ?? Random();
  return kSkillEpochMinN + rng.nextInt(kSkillEpochMaxN - kSkillEpochMinN + 1);
}

class SkillAdaptDecision {
  const SkillAdaptDecision({
    this.densityDelta = 0,
    this.tierDelta = 0,
    this.reason = 'hold',
  });
  final int densityDelta;
  final int tierDelta;
  final String reason;
}

/// Decide from [SkillState.epochMeans] once length ≥ [SkillState.epochTargetN].
SkillAdaptDecision decideSkillAdapt({
  required SkillState state,
  required List<String> baseChunks,
}) {
  if (state.cooldownBlocks > 0) {
    return const SkillAdaptDecision(reason: 'cooldown');
  }
  final target = state.epochTargetN.clamp(kSkillEpochMinN, kSkillEpochMaxN);
  if (state.epochMeans.length < target) {
    return const SkillAdaptDecision(reason: 'epoch_wait');
  }
  final means = state.epochMeans;
  final avg = means.reduce((a, b) => a + b) / means.length;
  final dens = state.density;
  final tier = state.tier;

  if (avg <= kSkillFinerThreshold) {
    if (canFiner(baseChunks, dens)) {
      return const SkillAdaptDecision(densityDelta: 1, reason: 'finer');
    }
    if (tier > 0) {
      return const SkillAdaptDecision(tierDelta: -1, reason: 'tier_down');
    }
    return const SkillAdaptDecision(reason: 'floor');
  }
  if (avg >= kSkillCoarserThreshold) {
    if (canCoarser(baseChunks, dens)) {
      return const SkillAdaptDecision(densityDelta: -1, reason: 'coarser');
    }
    if (tier < 9) {
      return const SkillAdaptDecision(tierDelta: 1, reason: 'tier_up');
    }
    return const SkillAdaptDecision(reason: 'ceiling');
  }
  return const SkillAdaptDecision(reason: 'hold');
}
