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

  test('watchdog is scheduled rest plus two seconds when there is no review', () {
    expect(
      restCoverWatchdogLimit(scheduledRest: const Duration(seconds: 15)),
      const Duration(seconds: 17),
    );
    expect(
      restCoverWatchdogLimit(scheduledRest: Duration.zero),
      kRestWatchdogSlack,
    );
  });

  test('watchdog covers five tries per review word plus tail plus slack', () {
    final one = kMissReviewAttemptBudget * kMissReviewMaxTries;
    expect(
      restCoverWatchdogLimit(
        scheduledRest: const Duration(seconds: 15),
        reviewWordN: 1,
      ),
      one + kMissReviewTail + kRestWatchdogSlack,
    );
    expect(
      restCoverWatchdogLimit(
        scheduledRest: const Duration(seconds: 15),
        reviewWordN: 2,
      ),
      one * 2 + kMissReviewTail + kRestWatchdogSlack,
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

  test('speak window is the time just heard plus two seconds', () {
    expect(
      missReviewSpeakWindow(const Duration(milliseconds: 800)),
      const Duration(milliseconds: 2800),
    );
    expect(
      missReviewSpeakWindow(Duration.zero),
      kMissReviewSpeakPad,
    );
  });

  test('a heard content word matches and a different word does not', () {
    expect(
      missReviewHeardMatches(expected: 'catalyst', heard: 'The catalyst.'),
      isTrue,
    );
    expect(
      missReviewHeardMatches(expected: 'catalyst', heard: 'vapor'),
      isFalse,
    );
    expect(missReviewHeardMatches(expected: 'catalyst', heard: ''), isFalse);
    expect(
      missReviewHeardMatches(expected: 'c v d', heard: 'v d'),
      isFalse,
    );
    expect(
      missReviewHeardMatches(expected: 'c v d', heard: 'c v d'),
      isTrue,
    );
    expect(missReviewHeardMatches(expected: 'is', heard: 'is'), isTrue);
  });

  test('a retry draw is not the voice and rate just heard', () {
    const voices = [
      'en-US-Neural2-A',
      'en-US-Neural2-D',
      'en-GB-Neural2-B',
    ];
    final first = drawMissReviewPlayback(
      randomAuto: true,
      reviewTier: 2,
      fallbackVoice: 'en-US-Neural2-D',
      fallbackRate: 1,
      voiceIds: voices,
      random: Random(3),
    );
    final again = drawMissReviewPlayback(
      randomAuto: true,
      reviewTier: 2,
      fallbackVoice: 'en-US-Neural2-D',
      fallbackRate: 1,
      voiceIds: voices,
      avoidVoice: first.voice,
      avoidRate: first.rate,
      random: Random(3),
    );
    final same = again.voice == first.voice &&
        (again.rate - first.rate).abs() < 0.001;
    expect(same, isFalse);
  });

  test('fixed voice stays on the first play', () {
    final play = drawMissReviewPlayback(
      randomAuto: false,
      reviewTier: 2,
      fallbackVoice: 'en-US-Neural2-D',
      fallbackRate: 0.9,
    );
    expect(play.voice, 'en-US-Neural2-D');
    expect(play.rate, 0.9);
  });
}
