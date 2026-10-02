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

/// The mark and the accuracy only draw while the replay phase is on screen, so
/// the phase stays this long counted from the end of the replay audio.
const Duration kReplayMarkHold = Duration(milliseconds: 2200);
const int kMissReviewMaxTries = 5;

/// design/384 - a sound drill is two tries, then the speaker climbs back.
const int kMissReviewSoundTries = 2;

/// Extra attempts the rest watchdog must leave room for: a few sounds, two
/// tries each, on top of the word tries. Without this the cover would close
/// while the speaker was still inside a sound drill.
const int kMissReviewSoundExtraAttempts = 8;
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

enum MissReviewHear { matched, missed, blank, skip }

/// Consecutive takes with nothing to compare before the word is let go.
///
/// A word the recognizer never returns text for used to burn all five tries.
const int kMissReviewBlankStop = 2;

/// Hard cap on the black rest cover. Past this, force the next listen.
Duration restCoverWatchdogLimit({
  required Duration scheduledRest,
  int reviewWordN = 0,
}) {
  if (reviewWordN <= 0) {
    if (scheduledRest <= Duration.zero) return kRestWatchdogSlack;
    return scheduledRest + kRestWatchdogSlack;
  }
  final reviewMax = kMissReviewAttemptBudget *
      (kMissReviewMaxTries + kMissReviewSoundExtraAttempts) *
      reviewWordN;
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

/// The heard symbols grouped the way the server sent them, one group per word.
List<String> missReviewHeardPhoneWords(String heardPhones) => [
      for (final part in heardPhones.split('|'))
        if (part.trim().isNotEmpty) part.trim(),
    ];

// design/370 — `missReviewHeardMatches`, `missReviewHeardTooLong`,
// `traceMissReview` and the `MissReviewTrace` they filled compared the asked-for
// word against a transcript. The review judges by sound now, so there is no
// transcript to compare and no need for the length gate that caught a recognizer
// writing the whole sentence from memory.

/// The sounds inside one word that did not line up with the target.
///
/// Empty when either side has no symbols, or when every sound already matches.
/// The review then drills the whole word instead of one sound.
List<String> phoneDrillTargets({
  required String target,
  required String heard,
}) {
  final want = _drillPieces(target);
  final got = _drillPieces(heard);
  if (want.isEmpty || got.isEmpty) return const [];
  final left = [...got];
  final out = <String>[];
  for (final piece in want) {
    final at = left.indexOf(piece);
    if (at >= 0) {
      left.removeAt(at);
      continue;
    }
    if (!out.contains(piece)) out.add(piece);
  }
  return out;
}

List<String> _drillPieces(String ipa) => phoneUnits(ipa);

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

/// One missed word: what is printed, what the model says, and its symbols.
/// design/376 — whether a take that missed words goes on to re-read them.
///
/// On by default: the drill is the point of marking a word missed. Off leaves the
/// marking alone — the word still shows as missed and still moves the score — and
/// only skips the re-reading, which is the part that costs time.
const String kMissReviewPrefKey = 'asr.practice.miss_review';

class MissReviewItem {
  const MissReviewItem({
    required this.printed,
    required this.spoken,
    required this.phone,
    this.sounds = const [],
  });

  final String printed;
  final String spoken;
  final String phone;

  /// design/384 — how sure the model was of each symbol in [phone], from the
  /// take that marked this word missed. Empty when it cannot be lined up.
  final List<double> sounds;

  /// What the review plays and compares. The speak phase scored the spoken
  /// form, so a printed `nm` is asked for as `nanometers`, not as two letters.
  String get ask => spoken.trim().isEmpty ? printed : spoken.trim();
}

/// Missed words for the red-miss spans. Invalid ranges are dropped.
List<MissReviewItem> missReviewWords({
  required String display,
  required List<MissedWordSpan> spans,
}) {
  final out = <MissReviewItem>[];
  for (final span in spans) {
    if (span.start < 0 || span.end <= span.start) continue;
    if (span.end > display.length) continue;
    final word = display.substring(span.start, span.end).trim();
    if (word.isEmpty) continue;
    out.add(MissReviewItem(
      printed: word,
      spoken: span.spoken,
      phone: span.phone,
      sounds: span.sounds,
    ));
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


/// design/384 - narrow the unit only after the same sound is missed twice.
///
/// A word score cannot say which sound to aim at. After two word tries that
/// both miss the same sound, this opens a drill for that sound. Passing it, or
/// using both tries, climbs back: another waiting sound if there is one, else
/// the word again.
class MissReviewLadder {
  MissReviewLadder({required this.soundN, required this.line})
      : _streak = List<int>.filled(soundN < 0 ? 0 : soundN, 0);

  final int soundN;
  final double line;
  final List<int> _streak;
  int? drilling;
  int drillTries = 0;

  /// Call only after a missed word try. [sounds] must line up with [soundN]
  /// or this returns null rather than open a drill on the wrong symbol.
  int? afterWord(List<double> sounds) {
    if (sounds.length != soundN || soundN <= 0) return null;
    for (var i = 0; i < soundN; i++) {
      _streak[i] = sounds[i] < line ? _streak[i] + 1 : 0;
    }
    return _openNext();
  }

  /// Call after a sound-drill try with that one sound's score.
  int? afterSound(double score) {
    final i = drilling;
    if (i == null) return null;
    drillTries += 1;
    if (score >= line || drillTries >= kMissReviewSoundTries) {
      _streak[i] = 0;
      return _openNext();
    }
    return i;
  }

  int? _openNext() {
    for (var i = 0; i < _streak.length; i++) {
      if (_streak[i] >= kMissReviewSoundTries) {
        if (drilling != i) drillTries = 0;
        drilling = i;
        return i;
      }
    }
    drilling = null;
    drillTries = 0;
    return null;
  }
}
