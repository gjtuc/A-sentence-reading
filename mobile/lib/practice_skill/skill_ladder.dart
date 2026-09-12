/// design/244 — practice skill ladder position (tier × density → n/50).
library;

import 'chunk_density.dart';

const int kSkillLadderTierMin = 0;
const int kSkillLadderTierMax = 9;
const int kSkillLadderTierCount = 10; // 0..9
const int kSkillLadderDensityCount = 5; // -2..2
const int kSkillLadderTotal = 50; // 10 * 5

int clampSkillTier(int tier) {
  if (tier < kSkillLadderTierMin) return kSkillLadderTierMin;
  if (tier > kSkillLadderTierMax) return kSkillLadderTierMax;
  return tier;
}

/// 0..29; higher = harder (density up = easier within a tier).
int skillLadderHardness0({required int tier, required int density}) {
  final t = clampSkillTier(tier);
  final d = clampChunkDensity(density);
  return t * kSkillLadderDensityCount + (2 - d);
}

/// 1..30 for UI.
int skillLadderDisplayN({required int tier, required int density}) =>
    skillLadderHardness0(tier: tier, density: density) + 1;

String skillLadderLabelKo({required int tier, required int density}) =>
    '난이도 ${skillLadderDisplayN(tier: tier, density: density)}/$kSkillLadderTotal';

/// Decode hardness0 for tests / debug.
({int tier, int density}) skillLadderDecode(int hardness0) {
  var h = hardness0;
  if (h < 0) h = 0;
  if (h > kSkillLadderTotal - 1) h = kSkillLadderTotal - 1;
  final tier = h ~/ kSkillLadderDensityCount;
  final density = 2 - (h % kSkillLadderDensityCount);
  return (tier: tier, density: density);
}
