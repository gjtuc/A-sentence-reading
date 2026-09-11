import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/practice_skill/skill_ladder.dart';

void main() {
  test('default tier2 density0 → 13/30', () {
    expect(skillLadderDisplayN(tier: 2, density: 0), 13);
    expect(skillLadderLabelKo(tier: 2, density: 0), '난이도 13/30');
  });

  test('easiest and hardest corners', () {
    expect(skillLadderDisplayN(tier: 0, density: 2), 1);
    expect(skillLadderDisplayN(tier: 5, density: -2), 30);
  });

  test('higher density is easier (lower n) within same tier', () {
    final fine = skillLadderDisplayN(tier: 2, density: 2);
    final coarse = skillLadderDisplayN(tier: 2, density: -2);
    expect(fine, lessThan(coarse));
    expect(fine, 11);
    expect(coarse, 15);
  });

  test('clamp out-of-range inputs', () {
    expect(skillLadderDisplayN(tier: 99, density: -9), 30);
    expect(skillLadderDisplayN(tier: -3, density: 9), 1);
  });

  test('decode round-trip 0..29', () {
    for (var h = 0; h < kSkillLadderTotal; h++) {
      final decoded = skillLadderDecode(h);
      expect(
        skillLadderHardness0(tier: decoded.tier, density: decoded.density),
        h,
      );
    }
  });
}
