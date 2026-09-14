import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/tts_models.dart';
import 'package:sentence_reading/practice_rhythm/blank_rest.dart';
import 'package:sentence_reading/practice_skill/chunk_density.dart';
import 'package:sentence_reading/practice_skill/skill_adapt.dart';
import 'package:sentence_reading/practice_skill/skill_store.dart';

void main() {
  group('blankRestDuration', () {
    test('N=3 steps are 5/10/15s', () {
      expect(
        blankRestDuration(chunkCountN: 3, step1Based: 1),
        const Duration(seconds: 5),
      );
      expect(
        blankRestDuration(chunkCountN: 3, step1Based: 2),
        const Duration(seconds: 10),
      );
      expect(
        blankRestDuration(chunkCountN: 3, step1Based: 3),
        const Duration(seconds: 15),
      );
    });

    test('N=1 is 15s', () {
      expect(
        blankRestDuration(chunkCountN: 1, step1Based: 1),
        const Duration(seconds: 15),
      );
    });

    test('rounds nearest ms for N=4 step1', () {
      expect(
        blankRestDuration(chunkCountN: 4, step1Based: 1),
        const Duration(milliseconds: 3750),
      );
    });
  });

  group('soft entry apply', () {
    test('tier_up sets density +2', () {
      final apply = resolveSkillAdaptApply(
        state: const SkillState(tier: 2, density: -2),
        decision: const SkillAdaptDecision(tierDelta: 1, reason: 'tier_up'),
      );
      expect(apply.changed, isTrue);
      expect(apply.softEntry, isTrue);
      expect(apply.tier, 3);
      expect(apply.density, kChunkDensityMax);
    });

    test('tier_down keeps density', () {
      final apply = resolveSkillAdaptApply(
        state: const SkillState(tier: 2, density: 1),
        decision: const SkillAdaptDecision(tierDelta: -1, reason: 'tier_down'),
      );
      expect(apply.changed, isTrue);
      expect(apply.softEntry, isFalse);
      expect(apply.tier, 1);
      expect(apply.density, 1);
    });
  });

  group('densitySkewUnit gmin 0.40', () {
    test('mean(+2) slower than mean(-2) same tier', () {
      final rng = Random(42);
      var sumSlow = 0.0;
      var sumFast = 0.0;
      const n = 4000;
      for (var i = 0; i < n; i++) {
        final u = rng.nextDouble();
        sumSlow += densitySkewUnit(u, 2);
        sumFast += densitySkewUnit(u, -2);
      }
      expect(sumSlow / n, lessThan(sumFast / n));
    });

    test('soft sawtooth mean(T,-2) > mean(T+1,+2)', () {
      final rng = Random(7);
      const draws = 8000;
      for (var t = 0; t < 9; t++) {
        final bandLo = kTtsSkillTier[t]!;
        final bandHi = kTtsSkillTier[t + 1]!;
        var meanLo = 0.0;
        var meanHi = 0.0;
        for (var i = 0; i < draws; i++) {
          final u = rng.nextDouble();
          final rLo = bandLo.$1 + densitySkewUnit(u, -2) * (bandLo.$2 - bandLo.$1);
          final rHi = bandHi.$1 + densitySkewUnit(u, 2) * (bandHi.$2 - bandHi.$1);
          meanLo += rLo;
          meanHi += rHi;
        }
        meanLo /= draws;
        meanHi /= draws;
        expect(
          meanLo,
          greaterThan(meanHi),
          reason: 'T$t→T${t + 1}: $meanLo vs $meanHi',
        );
      }
    });
  });
}
