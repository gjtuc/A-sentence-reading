import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/tts_models.dart';
import 'package:sentence_reading/practice_rhythm/miss_review.dart';
import 'package:sentence_reading/practice_skill/skill_score.dart';

void main() {
  test('review tier drops two steps and stays in 0..9', () {
    expect(missReviewTier(0), 0);
    expect(missReviewTier(1), 0);
    expect(missReviewTier(4), 2);
    expect(missReviewTier(9), 7);
  });

  test('review words keep order and drop a bad span', () {
    const text = 'The catalyst rose';
    final words = missReviewWords(
      display: text,
      spans: [
        MissedWordSpan(text.indexOf('catalyst'), text.indexOf('catalyst') + 8),
        const MissedWordSpan(-1, 2),
        MissedWordSpan(text.indexOf('rose'), text.indexOf('rose') + 4),
      ],
    );
    expect(words, ['catalyst', 'rose']);
  });

  test('review tail pads a short drill and adds 3s only when longer', () {
    expect(
      missReviewTail(
        scheduledRest: const Duration(seconds: 15),
        elapsed: const Duration(seconds: 2),
      ),
      const Duration(seconds: 13),
    );
    expect(
      missReviewTail(
        scheduledRest: const Duration(seconds: 5),
        elapsed: const Duration(seconds: 5),
      ),
      kMissReviewTail,
    );
    expect(
      missReviewTail(
        scheduledRest: Duration.zero,
        elapsed: const Duration(milliseconds: 400),
      ),
      kMissReviewTail,
    );
  });

  test('lower-tier draw stays in that band without a saved tier', () {
    final tier = missReviewTier(6);
    final band = kTtsSkillTier[tier]!;
    for (var i = 0; i < 12; i++) {
      final p = pickTtsPlaybackParams(
        mode: kTtsModeRandomAuto,
        voice: kTtsDefaultVoice,
        speakingRate: 1,
        skillTier: tier,
        applyDensityRateBias: false,
        random: Random(i),
      );
      expect(p.speakingRate, greaterThanOrEqualTo(band.$1));
      expect(p.speakingRate, lessThanOrEqualTo(band.$2));
    }
  });
}
