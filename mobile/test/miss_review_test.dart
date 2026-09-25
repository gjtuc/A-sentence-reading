import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/tts_models.dart';
import 'package:sentence_reading/practice_rhythm/follow_span.dart';
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
    expect(words.map((w) => w.printed), ['catalyst', 'rose']);
  });

  test('a review asks for the word the model reads, not the printed letters', () {
    const text = 'a 1 nm film';
    final words = missReviewWords(
      display: text,
      spans: [
        const MissedWordSpan(0, 1, spoken: 'a', phone: 'ɐ'),
        const MissedWordSpan(2, 3, spoken: 'one', phone: 'wˈʌn'),
        const MissedWordSpan(4, 6, spoken: 'nanometers', phone: 'nˈænoːmiːtɚz'),
      ],
    );
    expect(words.map((w) => w.printed), ['a', '1', 'nm']);
    expect(words.map((w) => w.ask), ['a', 'one', 'nanometers']);
    expect(words[2].phone, 'nˈænoːmiːtɚz');
  });

  test('a missed slot carries its spoken form and its symbols', () {
    const display = 'The 1 nm film';
    const spoken = 'The one nanometers film';
    final spans = [
      const FollowSpan(start: 0, end: 3, weight: 3, phone: 'ð ə'),
      const FollowSpan(start: 4, end: 5, weight: 3, phone: 'w ʌ n'),
      const FollowSpan(start: 6, end: 8, weight: 10, phone: 'n æ n'),
      const FollowSpan(start: 9, end: 13, weight: 4, phone: 'f ɪ l m'),
    ];
    final diag = diagnoseSpokenSlots(
      display: display,
      spoken: spoken,
      spans: spans,
      heard: 'The film',
    );
    final words = missReviewWords(
      display: display,
      spans: diag.score.missedSpans,
    );
    expect(words.map((w) => w.printed), ['1', 'nm']);
    expect(words.map((w) => w.ask), ['one', 'nanometers']);
    expect(words[1].phone, 'n æ n');
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

  test('review trace keeps the heard line beside each expected piece', () {
    final their = traceMissReview(
      expected: 'Their',
      heard: 'They are',
    );
    expect(their.matched, isTrue);
    expect(their.pieces, 'their');
    expect(their.hits, '1');

    final joined = traceMissReview(
      expected: 'C N T',
      heard: 'CNT',
    );
    expect(joined.matched, isTrue);
    expect(joined.pieces, 'c | n | t');
    expect(joined.hits, '111');
  });

  test('a drill picks only the sounds that did not line up', () {
    final drill = phoneDrillTargets(
      target: 'p l æ t ɪ n ə m',
      heard: 'p l e t n ə m',
    );
    expect(drill, contains('æ'));
    expect(drill, contains('ɪ'));
    expect(drill, isNot(contains('p')));

    expect(phoneDrillTargets(target: 'p l æ t', heard: 'p l æ t'), isEmpty);
    expect(phoneDrillTargets(target: 'p l æ t', heard: ''), isEmpty);
  });

  test('a sentence answered to a one-word ask is thrown away', () {
    expect(
      missReviewHeardTooLong(
        expected: 'iijima',
        heard: 'The purpose of this study is to examine the relationship',
      ),
      isTrue,
    );
    // A wrong answer of about the right length is a real attempt.
    expect(
      missReviewHeardTooLong(expected: 'displays', heard: 'This place'),
      isFalse,
    );
    expect(
      missReviewHeardTooLong(expected: 'c v d', heard: 'C B D'),
      isFalse,
    );
    expect(missReviewHeardTooLong(expected: 'the', heard: null), isFalse);
  });

  test('heard symbols split into the groups the server sent', () {
    expect(
      missReviewHeardPhoneWords('ð ə | d ɪ s p'),
      ['ð ə', 'd ɪ s p'],
    );
    expect(missReviewHeardPhoneWords(''), isEmpty);
  });
}
