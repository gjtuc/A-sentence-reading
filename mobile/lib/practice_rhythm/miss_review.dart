/// Missed-word review after replay (design/314) and rest-cover cap (design/320).
library;

import 'dart:math';

import '../api/tts_models.dart';
import '../practice_skill/skill_score.dart';

const Duration kMissReviewGap = Duration(milliseconds: 400);
const Duration kMissReviewTail = Duration(seconds: 3);
const Duration kMissReviewScoreWait = Duration(seconds: 20);
const Duration kMissReviewWordTimeout = Duration(seconds: 12);
const Duration kMissReviewMicReady = Duration(milliseconds: 350);
const Duration kMissReviewSpeakPad = Duration(seconds: 2);
const Duration kMissReviewSttWait = Duration(seconds: 8);
const int kMissReviewMaxTries = 5;
const Duration kRestWatchdogSlack = Duration(seconds: 2);

/// One play, one quiet speak window, and one STT wait.
/// The speak window can be as long as the play timeout plus the 2s pad.
Duration get kMissReviewAttemptBudget =>
    kMissReviewWordTimeout +
    kMissReviewMicReady +
    kMissReviewWordTimeout +
    kMissReviewSpeakPad +
    kMissReviewSttWait;

/// Mic stays closed during TTS. Recording is the time just heard, plus 2s.
Duration missReviewSpeakWindow(Duration ttsHeard) {
  final heard = ttsHeard < Duration.zero ? Duration.zero : ttsHeard;
  return heard + kMissReviewSpeakPad;
}

enum MissReviewHear { matched, missed, skip }

/// Hard cap on the black rest cover. Past this, force the next listen.
Duration restCoverWatchdogLimit({
  required Duration scheduledRest,
  int reviewWordN = 0,
}) {
  if (reviewWordN <= 0) {
    if (scheduledRest <= Duration.zero) return kRestWatchdogSlack;
    return scheduledRest + kRestWatchdogSlack;
  }
  final reviewMax =
      kMissReviewAttemptBudget * kMissReviewMaxTries * reviewWordN;
  final tail = missReviewTail(scheduledRest: scheduledRest, elapsed: reviewMax);
  return reviewMax + tail + kRestWatchdogSlack;
}

/// Lower random tier for review. Does not persist.
int missReviewTier(int applied) {
  final n = applied - 2;
  if (n < 0) return 0;
  if (n > 9) return 9;
  return n;
}

/// True when every spoken piece of [expected] was heard, including function words.
bool missReviewHeardMatches({required String expected, required String? heard}) {
  return traceMissReview(expected: expected, heard: heard).matched;
}

/// What the review compare saw: the expected pieces and a 1/0 for each.
MissReviewTrace traceMissReview({
  required String expected,
  required String? heard,
}) {
  final ref = tokenizeSkill(expected);
  final have = <String, int>{};
  for (final token in tokenizeSkill(heard)) {
    have[token] = (have[token] ?? 0) + 1;
  }
  if (ref.length >= 2 &&
      ref.every((token) => token.length == 1 && _reviewLetter.hasMatch(token))) {
    final joined = ref.join();
    if ((have[joined] ?? 0) > 0) {
      return MissReviewTrace(
        pieces: ref.join(' | '),
        hits: '1' * ref.length,
        matched: true,
      );
    }
  }
  final marks = StringBuffer();
  var matched = ref.isNotEmpty;
  for (final token in ref) {
    final left = have[token] ?? 0;
    if (left <= 0) {
      matched = false;
      marks.write('0');
      continue;
    }
    marks.write('1');
    if (left == 1) {
      have.remove(token);
    } else {
      have[token] = left - 1;
    }
  }
  return MissReviewTrace(
    pieces: ref.join(' | '),
    hits: marks.toString(),
    matched: matched,
  );
}

final RegExp _reviewLetter = RegExp(r'^\p{L}$', unicode: true);

class MissReviewTrace {
  const MissReviewTrace({
    required this.pieces,
    required this.hits,
    required this.matched,
  });

  final String pieces;
  final String hits;
  final bool matched;
}

/// Voice and rate for one review play.
///
/// The first play follows [randomAuto]. A retry always draws the lower
/// random tier and does not repeat the voice and rate just heard.
({String voice, double rate}) drawMissReviewPlayback({
  required bool randomAuto,
  required int reviewTier,
  required String fallbackVoice,
  required double fallbackRate,
  List<String> voiceIds = const [],
  String? avoidVoice,
  double? avoidRate,
  Random? random,
  int redraws = 8,
}) {
  if (!randomAuto) {
    final voice = fallbackVoice.trim().isEmpty
        ? kTtsDefaultVoice
        : fallbackVoice.trim();
    return (voice: voice, rate: clampSpeakingRate(fallbackRate));
  }
  final rng = random ?? Random();
  ({String voice, double rate})? last;
  for (var i = 0; i < redraws; i++) {
    final picked = pickTtsPlaybackParams(
      mode: kTtsModeRandomAuto,
      voice: fallbackVoice,
      speakingRate: kTtsRateDefault,
      voiceIds: voiceIds,
      skillTier: reviewTier,
      applyDensityRateBias: false,
      random: rng,
    );
    last = (voice: picked.voice, rate: picked.speakingRate);
    final sameVoice = avoidVoice != null && picked.voice == avoidVoice;
    final sameRate = avoidRate != null &&
        (picked.speakingRate - avoidRate).abs() < 0.001;
    if (!(sameVoice && sameRate)) return last;
  }
  return last!;
}

/// Printed tokens for the red-miss spans. Invalid ranges are dropped.
List<String> missReviewWords({
  required String display,
  required List<MissedWordSpan> spans,
}) {
  final out = <String>[];
  for (final span in spans) {
    if (span.start < 0 || span.end <= span.start) continue;
    if (span.end > display.length) continue;
    final word = display.substring(span.start, span.end).trim();
    if (word.isEmpty) continue;
    out.add(word);
  }
  return out;
}

/// Blank wait after the words. Three seconds only when the review ran long.
Duration missReviewTail({
  required Duration scheduledRest,
  required Duration elapsed,
}) {
  if (elapsed >= scheduledRest) return kMissReviewTail;
  return scheduledRest - elapsed;
}
