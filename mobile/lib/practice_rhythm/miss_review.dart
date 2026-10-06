/// Missed-word review after replay (design/314) and rest-cover cap (design/320).
library;

import 'dart:math';

import '../api/tts_models.dart';
import '../practice_skill/skill_score.dart';
import 'follow_span.dart';

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

/// design/393 - word tries and sound drills together, per missed word.
const int kMissReviewTotalTries = 7;

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
    this.share = '',
    this.tops = const [],
  });

  final String printed;
  final String spoken;
  final String phone;

  /// design/384 — how sure the model was of each symbol in [phone], from the
  /// take that marked this word missed. Empty when it cannot be lined up.
  final List<double> sounds;

  /// design/388 — the native spread for [phone], sent back with the re-read.
  final String share;

  /// design/388 — stage one's pairs for each sound in [sounds].
  final List<List<SoundTop>> tops;

  /// What the review plays and compares. The speak phase scored the spoken
  /// form, so a printed `nm` is asked for as `nanometers`, not as two letters.
  String get ask => spoken.trim().isEmpty ? printed : spoken.trim();
}

/// design/390 — how long a word waits for its own reference before the review
/// falls back to the sentence's, and how often it asks.
const Duration kMissReviewRefWait = Duration(seconds: 12);
const Duration kMissReviewRefPoll = Duration(milliseconds: 1500);

/// design/390 — [item] judged against the word read on its own.
///
/// The review plays the word alone, and alone it is read in its citation form.
/// Inside the sentence `onto` before `CNT` was `ʌ n d ə`; alone it is `ɑ n t u`.
/// Judging a copy of the second against the first failed a speaker for repeating
/// exactly what they heard. [spans] are the word's own `/api/tts/spoken` spans.
///
/// The sentence take's per-sound scores belong to the sentence's symbols, so
/// they are dropped. Null when the word's reference has no symbols yet.
MissReviewItem? withOwnReference(MissReviewItem item, List<FollowSpan> spans) {
  final phones = <String>[];
  final shares = <String>[];
  for (final span in spans) {
    final phone = span.phone.trim();
    if (phone.isEmpty) continue;
    phones.add(phone);
    shares.add(span.share.trim());
  }
  if (phones.isEmpty) return null;
  final phone = phones.join(' ');
  final share = shares.join(',');
  final lined = shares.every((one) => one.isNotEmpty) &&
      share.split(',').length == phoneSymbols(phone).length;
  return MissReviewItem(
    printed: item.printed,
    spoken: item.spoken,
    phone: phone,
    share: lined ? share : '',
  );
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
      share: span.share,
      tops: span.tops,
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


/// design/393 - the one sound the next try aims at: the least sure of the
/// sounds that failed, or null when none did.
///
/// [tops] that do not line up leave every sound to the line. Ties go to the
/// earlier sound.
int? lowestMissedSound(
  List<double> sounds, {
  List<List<SoundTop>> tops = const [],
  required double line,
  double bar = 1.0,
}) {
  final lined = tops.length == sounds.length;
  int? at;
  for (var i = 0; i < sounds.length; i++) {
    final cleared = soundClears(
      sounds[i],
      top: lined ? tops[i] : const [],
      bar: bar,
      line: line,
    );
    if (cleared) continue;
    if (at == null || sounds[i] < sounds[at]) at = i;
  }
  return at;
}

enum MissReviewStep { word, sound, done }

/// design/393 - a missed word drops to its weakest sound, and a cleared sound
/// climbs back to the word.
///
/// A missed word try opens a drill on [lowestMissedSound] of that take. A drill
/// that misses aims at the weakest sound of its own take, which may be another
/// one. A drill that clears returns to the word. The word passing ends it, and
/// so does [maxTries] word and sound tries together.
class MissReviewClimb {
  MissReviewClimb({this.maxTries = kMissReviewTotalTries});

  final int maxTries;
  int tries = 0;
  int? focus;
  bool passed = false;

  MissReviewStep get step {
    if (passed || tries >= maxTries) return MissReviewStep.done;
    return focus == null ? MissReviewStep.word : MissReviewStep.sound;
  }

  /// [lowest] is null when the take gave nothing to aim at, and the word is
  /// tried again.
  void afterWord({required bool matched, int? lowest}) {
    tries += 1;
    if (matched) {
      passed = true;
      focus = null;
      return;
    }
    focus = lowest;
  }

  /// [cleared] is the drilled sound alone. A miss with no fresh [lowest]
  /// keeps the same sound.
  void afterSound({required bool cleared, int? lowest}) {
    tries += 1;
    focus = cleared ? null : (lowest ?? focus);
  }
}
