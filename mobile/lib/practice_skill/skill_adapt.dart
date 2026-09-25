/// design/212+215+274 — adapt density / tier from epoch of focus-block means.
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

/// design/274 — apply decide() with soft entry / asymmetric tier_down.
class SkillAdaptApply {
  const SkillAdaptApply({
    required this.tier,
    required this.density,
    required this.cooldown,
    required this.changed,
    this.softEntry = false,
    this.densityBefore = 0,
  });
  final int tier;
  final int density;
  final int cooldown;
  final bool changed;
  final bool softEntry;
  final int densityBefore;
}

SkillAdaptApply resolveSkillAdaptApply({
  required SkillState state,
  required SkillAdaptDecision decision,
}) {
  final densityBefore = state.density;
  if (decision.reason == 'epoch_wait' ||
      decision.reason == 'cooldown' ||
      decision.reason == 'pinned') {
    return SkillAdaptApply(
      tier: state.tier,
      density: state.density,
      cooldown: state.cooldownBlocks,
      changed: false,
      densityBefore: densityBefore,
    );
  }
  if (decision.densityDelta == 0 && decision.tierDelta == 0) {
    return SkillAdaptApply(
      tier: state.tier,
      density: state.density,
      cooldown: state.cooldownBlocks,
      changed: false,
      densityBefore: densityBefore,
    );
  }
  final tier = (state.tier + decision.tierDelta).clamp(0, 9);
  late final int density;
  var softEntry = false;
  if (decision.reason == 'tier_up') {
    density = kChunkDensityMax; // +2 soft entry
    softEntry = true;
  } else if (decision.reason == 'tier_down') {
    density = state.density; // keep (asymmetric)
  } else {
    density = clampChunkDensity(state.density + decision.densityDelta);
  }
  final cooldown =
      decision.tierDelta != 0 ? 1 : state.cooldownBlocks;
  return SkillAdaptApply(
    tier: tier,
    density: density,
    cooldown: cooldown,
    changed: true,
    softEntry: softEntry,
    densityBefore: densityBefore,
  );
}

/// Decide from [SkillState.epochMeans] once length ≥ [SkillState.epochTargetN].
SkillAdaptDecision decideSkillAdapt({
  required SkillState state,
  required List<String> baseChunks,
}) {
  // design/364 — a sample sweep asks for one rung and must stay on it. Left
  // adapting, an easy round would climb and a hard one fall mid-measurement.
  if (state.pinned) {
    return const SkillAdaptDecision(reason: 'pinned');
  }
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
