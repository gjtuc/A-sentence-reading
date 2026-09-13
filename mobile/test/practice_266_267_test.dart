import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/shadowing_chunk_plan.dart';
import 'package:sentence_reading/api/tts_models.dart';

void main() {
  group('design/266 playable', () {
    test('missing plan row is not playable', () {
      expect(
        shadowingChunksForSentence({'status': 'pending', 'sentences': {}}, 'x', 'Hi'),
        isEmpty,
      );
      expect(
        shadowingChunksForSentence(
          {'status': 'pending', 'sentences': {}},
          'x',
          'Hi',
          allowPlainFallback: true,
        ),
        ['Hi'],
      );
    });

    test('count ready and skip only plan rows', () {
      final plan = {
        'status': 'pending',
        'sentences': {
          '0': {
            'chunks': ['a', 'ab'],
          },
        },
      };
      expect(countShadowingReadySentences(plan), 1);
      final rows = [
        (id: '0', text: 'a b'),
        (id: '1', text: 'later'),
      ];
      expect(
        shadowingSkipEmptyDelta(plan: plan, sentences: rows, fromIndex: 0),
        0,
      );
      expect(
        shadowingSkipEmptyDelta(plan: plan, sentences: rows, fromIndex: 1),
        -1,
      );
    });

    test('mergeShadowingPlans unions sentences', () {
      final a = {
        'status': 'pending',
        'sentences': {
          '0': {
            'chunks': ['a'],
          },
        },
      };
      final b = {
        'status': 'pending',
        'sentences': {
          '1': {
            'chunks': ['b'],
          },
        },
      };
      final m = mergeShadowingPlans(a, b);
      expect(countShadowingReadySentences(m), 2);
    });
  });

  group('design/267 rate bias', () {
    test('density +2 mean slower than density -2', () {
      final rng = Random(42);
      double meanFor(int density) {
        var sum = 0.0;
        const n = 400;
        for (var i = 0; i < n; i++) {
          final p = pickTtsPlaybackParams(
            mode: kTtsModeRandomAuto,
            voice: kTtsDefaultVoice,
            speakingRate: 1.0,
            random: rng,
            skillTier: 2,
            practiceDensity: density,
            applyDensityRateBias: true,
          );
          sum += p.speakingRate;
        }
        return sum / n;
      }

      final slow = meanFor(2);
      final fast = meanFor(-2);
      expect(slow < fast, isTrue, reason: 'slow=$slow fast=$fast');
      final band = kTtsSkillTier[2]!;
      expect(slow, greaterThanOrEqualTo(band.$1 - 0.01));
      expect(fast, lessThanOrEqualTo(band.$2 + 0.01));
    });

    test('bias off matches band interior', () {
      final p = pickTtsPlaybackParams(
        mode: kTtsModeRandomAuto,
        voice: kTtsDefaultVoice,
        speakingRate: 1.0,
        random: Random(7),
        skillTier: 2,
        practiceDensity: 2,
        applyDensityRateBias: false,
      );
      final band = kTtsSkillTier[2]!;
      expect(p.speakingRate, greaterThanOrEqualTo(band.$1));
      expect(p.speakingRate, lessThanOrEqualTo(band.$2));
    });
  });
}
