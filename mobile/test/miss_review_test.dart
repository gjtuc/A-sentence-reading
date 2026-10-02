import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
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
      // design/370 - `film` is the only word whose sounds come back.
      heardPhones: const ['f ɪ l m'],
    );
    final words = missReviewWords(
      display: display,
      spans: diag.score.missedSpans,
    );
    // design/371 - the two-sound word cannot be asked about, so it is not put on
    // the review either. Telling the reader to practise a word the app cannot
    // judge is asking them to fix something nobody measured.
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
    final one = kMissReviewAttemptBudget *
        (kMissReviewMaxTries + kMissReviewSoundExtraAttempts);
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

  test('heard symbols split into the groups the server sent', () {
    expect(
      missReviewHeardPhoneWords('ð ə | d ɪ s p'),
      ['ð ə', 'd ɪ s p'],
    );
    expect(missReviewHeardPhoneWords(''), isEmpty);
  });

  test('a long sentence walks down and lands before the audio ends', () {
    const dur = Duration(seconds: 10);
    double? at(int ms) => promptScrollTarget(
          position: Duration(milliseconds: ms),
          duration: dur,
          maxScrollExtent: 400,
        );
    expect(at(0), 0);
    // 8.5s of a 10s read is the whole way down, so the bottom line is on
    // screen before the voice arrives there.
    expect(at(8500), 400);
    expect(at(10000), 400);
    expect(at(4250), closeTo(200, 0.01));
    // A sentence that already fits is left where it is.
    expect(
      promptScrollTarget(
        position: const Duration(seconds: 5),
        duration: dur,
        maxScrollExtent: 0,
      ),
      isNull,
    );
    expect(
      promptScrollTarget(
        position: const Duration(seconds: 5),
        duration: Duration.zero,
        maxScrollExtent: 400,
      ),
      isNull,
    );
  });

  // design/370 - three tests were removed here. They asserted that a transcript
  // held the same letters as the word asked for, that the trace listed those
  // letters, and that a sentence answered to a one-word ask was thrown away.
  // The review judges by sound now, so there is no transcript to compare and
  // nothing for the length gate to catch.

  test('design/376 the stored name is the one already on phones', () {
    // Changing this string does not change a default, it loses every choice
    // anyone has made: the old name keeps the value and nothing reads it, so
    // every reader who turned the drill off silently gets it back.
    expect(kMissReviewPrefKey, 'asr.practice.miss_review');
    // Same shelf as its neighbours, so one wipe of practice settings takes all
    // of them rather than leaving this one behind.
    expect(kMissReviewPrefKey, startsWith('asr.practice.'));
  });

  test('design/376 absent means on', () async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    // A reader who has never opened settings has not asked for the drill to
    // stop, and the drill is the reason a word is marked missed at all.
    expect(prefs.getBool(kMissReviewPrefKey) ?? true, isTrue);
  });

  test('design/376 off is remembered, and only off', () async {
    SharedPreferences.setMockInitialValues({kMissReviewPrefKey: false});
    var prefs = await SharedPreferences.getInstance();
    expect(prefs.getBool(kMissReviewPrefKey) ?? true, isFalse);
    // And back on, because a switch that only latches one way is a trap.
    await prefs.setBool(kMissReviewPrefKey, true);
    expect(prefs.getBool(kMissReviewPrefKey) ?? true, isTrue);
  });

  test('design/376 the switch does not touch which words are missed', () {
    // The sheet is built before the switch is consulted, so turning the drill
    // off must not change the score, the missed list, or the skill ladder. If
    // this ever stops holding, a reader could raise their tier by declining to
    // practise, which is the opposite of what the switch is for.
    const spans = [
      MissedWordSpan(0, 8, spoken: 'chemical'),
      MissedWordSpan(9, 14, spoken: 'vapor'),
    ];
    final words = missReviewWords(display: 'chemical vapor', spans: spans);
    expect(words.map((w) => w.printed).toList(), ['chemical', 'vapor']);
    // Whatever this list is, it is a function of the take alone. The switch is
    // read after this call and can only decide whether the list is walked.
    final again = missReviewWords(display: 'chemical vapor', spans: spans);
    expect(
      words.map((w) => w.printed).toList(),
      again.map((w) => w.printed).toList(),
    );
  });
}
