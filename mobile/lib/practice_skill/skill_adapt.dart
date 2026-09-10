/// design/212 — adapt density / tier from block means.
library;

import 'chunk_density.dart';
import 'skill_store.dart';

const int kSkillMinScoredN = 5;
const double kSkillFinerThreshold = 0.60;
const double kSkillCoarserThreshold = 0.75;

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

SkillAdaptDecision decideSkillAdapt({
  required SkillState state,
  required List<String> baseChunks,
}) {
  if (state.cooldownBlocks > 0) {
    return const SkillAdaptDecision(reason: 'cooldown');
  }
  if (state.blockN < kSkillMinScoredN) {
    return const SkillAdaptDecision(reason: 'low_n');
  }
  final avg = state.blockSum / state.blockN;
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
    if (tier < 5) {
      return const SkillAdaptDecision(tierDelta: 1, reason: 'tier_up');
    }
    return const SkillAdaptDecision(reason: 'ceiling');
  }
  return const SkillAdaptDecision(reason: 'hold');
}
