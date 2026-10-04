/// design/212 — content-word multiset coverage (mirrors practice_skill_score.py).
library;

import 'dart:math' as math;

import '../practice_rhythm/follow_span.dart';
import 'pass_line.dart';
import 'skill_ladder.dart';

const int kContentWordListV = 1;
const int kSpokenSlotListV = 2;

const Set<String> kFunctionWords = {
  'a', 'an', 'the', 'and', 'or', 'but', 'if', 'in', 'on', 'at', 'to', 'for',
  'of', 'as', 'by', 'with', 'from', 'into', 'onto', 'over', 'under', 'is',
  'are', 'was', 'were', 'be', 'been', 'being', 'am', 'do', 'does', 'did',
  'have', 'has', 'had', 'will', 'would', 'shall', 'should', 'can', 'could',
  'may', 'might', 'must', 'that', 'this', 'these', 'those', 'it', 'its',
  'they', 'them', 'their', 'we', 'our', 'you', 'your', 'he', 'she', 'his',
  'her', 'i', 'me', 'my', 'not', 'no', 'nor', 'so', 'than', 'then', 'there',
  'here', 'when', 'where', 'which', 'who', 'whom', 'what', 'how', 'also',
  'just', 'only', 'very', 'too', 'up', 'out', 'about', 'such', 'per',
};

final RegExp _tagRe = RegExp(r'<[^>]+>');
final RegExp _punctRe = RegExp(r"[^\w\s']+", unicode: true);
final RegExp _spaceRe = RegExp(r'\s+');

String normalizeSkillText(String? text) {
  if (text == null) return '';
  var t = _tagRe.allMatches(text).isEmpty
      ? text
      : text.replaceAll(_tagRe, ' ');
  t = t.toLowerCase().replaceAll('\u2019', "'").replaceAll('\u2018', "'");
  t = t.replaceAll(_punctRe, ' ');
  t = t.replaceAll(_spaceRe, ' ').trim();
  return t;
}

List<String> tokenizeSkill(String? text) {
  final n = normalizeSkillText(text);
  if (n.isEmpty) return const [];
  return n.split(' ');
}

List<String> contentWords(String? text) {
  return tokenizeSkill(text)
      .where((w) => w.isNotEmpty && !kFunctionWords.contains(w))
      .toList(growable: false);
}

class MissedWordSpan {
  const MissedWordSpan(
    this.start,
    this.end, {
    this.spoken = '',
    this.phone = '',
    this.sounds = const [],
    this.share = '',
    this.tops = const [],
  });

  final int start;
  final int end;

  /// What the model reads for this printed word (`nm` -> `nanometers`, `1` ->
  /// `one`). The speak phase scores this form, so the review has to ask for the
  /// same sound instead of the printed letters.
  final String spoken;

  /// Symbols for this slot, already cut by the server. Looking them up again by
  /// searching the sentence for the printed text lands inside another word when
  /// the word is one letter.
  final String phone;

  /// design/384 — how sure the model was of each symbol in [phone], same order.
  ///
  /// Empty when the server said nothing, or when it reported a different number
  /// of sounds than [phone] holds. A sound the model's vocabulary does not carry
  /// is dropped server-side, and lining the two up anyway would paint the wrong
  /// symbol red — worse than painting none.
  final List<double> sounds;

  /// design/388 — the native spread row for this slot. Empty on an older
  /// reference.
  final String share;

  /// design/388 — stage one's pairs for each sound in [sounds], same order.
  /// Empty when the server sent none, which leaves every sound to the line.
  final List<List<SoundTop>> tops;
}

/// design/388 — one native symbol at 20% or more, and the reader's share of it.
/// Both are blank-free and scaled to 1.
class SoundTop {
  const SoundTop(this.native, this.reader);

  final double native;
  final double reader;
}

class SkillScoreResult {
  const SkillScoreResult({
    required this.ok,
    this.accuracy,
    this.refN = 0,
    this.hitN = 0,
    this.error,
    this.listV = kContentWordListV,
    this.missedSpans = const [],
  });

  final bool ok;
  final double? accuracy;
  final int refN;
  final int hitN;
  final String? error;
  final int listV;
  final List<MissedWordSpan> missedSpans;

  SkillScoreResult copyWith({List<MissedWordSpan>? missedSpans}) {
    return SkillScoreResult(
      ok: ok,
      accuracy: accuracy,
      refN: refN,
      hitN: hitN,
      error: error,
      listV: listV,
      missedSpans: missedSpans ?? this.missedSpans,
    );
  }
}

// design/370 - contentWordCoverage and missedContentSpans were the design/212
// v1 scorer. Both counted words in a transcript, which is the question this
// app stopped asking. Nothing on the live path called either one.

class SpokenSlotDiag {
  const SpokenSlotDiag({
    required this.score,
    required this.slotCode,
    required this.spanN,
    required this.posSpanN,
    required this.walkI,
    required this.pieceWeight,
    required this.remain,
    this.slotHits = '',
    this.slotPieces = '',
    this.soundPassN = 0,
    this.wordScores = const [],
    this.slotScores = '',
  });

  final SkillScoreResult score;
  final String slotCode;
  final int spanN;
  final int posSpanN;
  final int walkI;
  final int pieceWeight;
  final int remain;
  final String slotHits;
  final String slotPieces;

  /// Slots that only the sound let through, the word itself having missed.
  ///
  /// The hit marks alone cannot say which side passed a slot, so a compare that
  /// is too generous would be invisible.
  final int soundPassN;

  /// What each judged word scored, for the account to draw its next line from.
  final List<double> wordScores;

  /// How close each slot came, in hundredths, one field per slot in the order
  /// [slotHits] uses, with `-` where the word could not be asked about.
  ///
  /// design/377 — the marks alone cannot say whether a word was refused by a
  /// hair or by a mile, and those want different fixes. A reader asked why a
  /// sentence came back evenly wrong and the log could not answer: rebuilding the
  /// numbers afterwards needed the reference, the take, and this file's own unit
  /// rules, which is too much to ask of anyone reading a log.
  final String slotScores;
}

/// One printed word is one score slot, including function words.
///
/// A printed token spoken as several pieces (`CVD` → `c v d`, `Pt` →
/// `platinum`) is still one slot. Any missing piece fails the whole slot.
SpokenSlotDiag diagnoseSpokenSlots({
  required String display,
  required String spoken,
  required List<FollowSpan> spans,
  List<String> heardPhones = const [],
  double passLine = kPassLineCold,
  // design/387 — first gate. 1.0 leaves a caller that does not pass a rung
  // judging by the account line alone.
  double difficultyBar = 1.0,
  List<int> slotSaid = const [],
  // design/382 — one score per slot from the server, which has the model's own
  // probabilities. Empty, short, or long and the sounds are compared here the
  // way they shipped, so an old server or a failed alignment costs nothing.
  List<double> soundScores = const [],
  List<List<double>> soundEach = const [],
  // design/388 — stage one's pairs, per slot and per sound.
  List<List<List<SoundTop>>> soundTops = const [],
}) {
  final built = _spokenSlots(display: display, spoken: spoken, spans: spans);
  if (built.slots.isEmpty) {
    return SpokenSlotDiag(
      score: SkillScoreResult(
        ok: false,
        error: built.code,
        listV: kSpokenSlotListV,
      ),
      slotCode: built.code,
      spanN: built.spanN,
      posSpanN: built.posSpanN,
      walkI: built.walkI,
      pieceWeight: built.pieceWeight,
      remain: built.remain,
    );
  }
  // design/366 — hand over the whole run of sounds. `phonesClose` walks it, so
  // cutting it per word here only threw the tail away.
  final heardPhoneWords = [
    for (final phone in heardPhones) phone.trim(),
  ].where((phone) => phone.isNotEmpty).toList();
  // design/370 — a slot is judged by sound alone now. The transcript compare is
  // gone: it asked whether a model typed the same letters, which is a different
  // question from whether the word was pronounced. With no reference sound there
  // is nothing to compare against, and saying "all wrong" would be a lie, so the
  // take goes back unscored and the caller records that.
  final refN = built.slots.where((slot) => slot.phone.trim().isNotEmpty).length;
  if (refN == 0) {
    return SpokenSlotDiag(
      score: SkillScoreResult(
        ok: false,
        error: kSoundRefMissing,
        listV: kSpokenSlotListV,
      ),
      slotCode: kSoundRefMissing,
      spanN: built.spanN,
      posSpanN: built.posSpanN,
      walkI: built.walkI,
      pieceWeight: built.pieceWeight,
      remain: built.remain,
    );
  }
  var hit = 0;
  var judged = 0;
  var soundPassN = 0;
  final scores = <double>[];
  final missed = <MissedWordSpan>[];
  final marks = StringBuffer();
  final pieces = <String>[];
  final closeness = <String>[];
  final fromServer = soundScores.length == built.slots.length;
  for (var slotI = 0; slotI < built.slots.length; slotI++) {
    final slot = built.slots[slotI];
    // design/382 — the server scored the sounds with the probabilities it has.
    // The too-short rule stays here either way: it is about the reference, not
    // about the reading, and a word two sounds long matches almost anything.
    final got = fromServer
        ? (_phonePieces(slot.phone).length < kPhoneMinUnits
            ? -1.0
            : soundScores[slotI])
        : phoneOverlap(slot.phone, heardPhoneWords);
    if (got < 0) {
      // design/371 - two sounds match almost anything, so this word cannot be
      // asked about at all. It used to be marked wrong, which failed every 	he
      // and  on every take, 3.6% of all words, and put them on the practice
      // list forever. A question we cannot put leaves the sheet instead of being
      // counted against the reader.
      marks.write('-');
      pieces.add(slot.tokens.join(' '));
      // design/377 -- a dash here too, so the two strings stay readable side by
      // side. A 0 would claim the word was asked and scored nothing.
      closeness.add('-');
      continue;
    }
    judged += 1;
    final probs = slotI < soundEach.length ? soundEach[slotI] : const <double>[];
    final soundN = phoneSymbols(slot.phone).length;
    // design/388 — the line learns each sound's overlap, because stage two
    // compares a sound's overlap with it. The difficulty bar must not move it,
    // or an easy rung would raise the line for a hard one. Without the
    // per-sound row the word's own overlap stands in, once.
    if (probs.length == soundN) {
      scores.addAll(probs);
    } else {
      scores.add(got);
    }
    final tops = slotI < soundTops.length
        ? soundTops[slotI]
        : const <List<SoundTop>>[];
    final said = slotI < slotSaid.length ? slotSaid[slotI] : -1;
    final adjusted = twoGateWordScore(
      probs: probs,
      tops: tops,
      soundN: soundN,
      said: said,
      bar: difficultyBar,
      line: passLine,
    );
    final shown = adjusted ?? got;
    closeness.add('${(shown * 100).round()}');
    final ok = shown >=
        (fromServer ? passLine : math.max(passLine, kWordOverlapLine));
    if (ok) soundPassN += 1;
    marks.write(ok ? '1' : '0');
    pieces.add(slot.tokens.join(' '));
    if (ok) {
      hit += 1;
    } else {
      final heardEach = slotI < soundEach.length
          ? soundEach[slotI]
          : const <double>[];
      missed.add(MissedWordSpan(
        slot.start,
        slot.end,
        spoken: slot.tokens.join(' '),
        phone: slot.phone,
        share: slot.share,
        sounds: heardEach.length == soundN ? heardEach : const <double>[],
        tops: heardEach.length == soundN && tops.length == soundN
            ? tops
            : const <List<SoundTop>>[],
      ));
    }
  }
  if (judged == 0) {
    // Every word's reference was too short. Saying "all wrong" would be a lie.
    return SpokenSlotDiag(
      score: SkillScoreResult(
        ok: false,
        error: kSoundTooShort,
        listV: kSpokenSlotListV,
      ),
      slotCode: kSoundTooShort,
      spanN: built.spanN,
      posSpanN: built.posSpanN,
      walkI: built.walkI,
      pieceWeight: built.pieceWeight,
      remain: built.remain,
      slotHits: marks.toString(),
      slotPieces: pieces.join(' | '),
      slotScores: closeness.join(' '),
    );
  }
  final acc = hit / judged;
  return SpokenSlotDiag(
    score: SkillScoreResult(
      ok: true,
      accuracy: (acc * 10000).round() / 10000.0,
      refN: judged,
      hitN: hit,
      listV: kSpokenSlotListV,
      missedSpans: missed,
    ),
    slotCode: 'ok',
    spanN: built.spanN,
    posSpanN: built.posSpanN,
    walkI: built.walkI,
    pieceWeight: built.pieceWeight,
    remain: built.remain,
    slotHits: marks.toString(),
    slotPieces: pieces.join(' | '),
    soundPassN: soundPassN,
    wordScores: scores,
    slotScores: closeness.join(' '),
  );
}

/// Score only. Diagnostics live on [diagnoseSpokenSlots].
SkillScoreResult spokenSlotCoverage({
  required String display,
  required String spoken,
  required List<FollowSpan> spans,
  List<String> heardPhones = const [],
}) {
  return diagnoseSpokenSlots(
    display: display,
    spoken: spoken,
    spans: spans,
    heardPhones: heardPhones,
  ).score;
}

/// design/382 — the reference sounds, one entry per score slot, in slot order.
///
/// The server has to answer in the order the slots are in, and the only way to be
/// sure of that is to ask with the slots themselves rather than with the spans
/// they were built from: a punctuation-only piece opens no slot, and a span
/// pointing outside the printed line opens none either. Slots whose reference is
/// too short to ask about are sent anyway, because the next word's first sound is
/// what ends this word's window and a gap in the lattice would lose it.
List<String> slotPhonesFor({
  required String display,
  required String spoken,
  required List<FollowSpan> spans,
}) {
  final built = _spokenSlots(display: display, spoken: spoken, spans: spans);
  return [for (final slot in built.slots) slot.phone.trim()];
}

/// design/386 — the native share row, one entry per score slot.
///
/// Empty when any slot that has sounds is missing its share, or a share does
/// not have one slot per sound. Sending a short row would line a sound up
/// with its neighbour.
List<String> slotSharesFor({
  required String display,
  required String spoken,
  required List<FollowSpan> spans,
}) {
  final built = _spokenSlots(display: display, spoken: spoken, spans: spans);
  final out = <String>[];
  for (final slot in built.slots) {
    final n = phoneSymbols(slot.phone).length;
    final share = slot.share.trim();
    if (n == 0) {
      out.add('');
      continue;
    }
    if (share.isEmpty || share.split(',').length != n) return const [];
    out.add(share);
  }
  return out;
}

/// design/382 — the server's `slot_sym` row as numbers, one per slot.
///
/// `-` means the word could not be asked about, which is -1 here, the same thing
/// [phoneOverlap] returns for it. A row that does not have one entry per slot is
/// refused whole: a scorer that silently slid by one would judge every word by
/// its neighbour's sounds.
/// design/384 — one slot's symbols, split the way the server split them.
///
/// The ask goes out as whitespace-separated symbols and the server does a plain
/// `split()`, so counting any other way would not line up with what comes back.
/// [phoneUnits] merges tie bars and marks, which is right for comparing sounds
/// and wrong for counting the server's columns.
List<String> phoneSymbols(String ipa) => [
      for (final one in ipa.trim().split(RegExp(r'\s+')))
        if (one.isNotEmpty) one,
    ];

/// design/384 — the per-sound row: words barred apart, sounds inside spaced.
///
/// `95 88 11|76 80|-` is three words. A barred `-` is a word the model knows no
/// sound for and comes back empty. Refuses the whole row when the word count
/// does not match, exactly as [parseSlotScores] does: a row out of step would
/// paint one word's sounds onto another.
List<List<double>> parseSlotSounds(String row, {required int slotN}) {
  final parts = row.trim().split('|');
  if (parts.length != slotN) return const [];
  final out = <List<double>>[];
  for (final part in parts) {
    final one = part.trim();
    if (one == '-' || one.isEmpty) {
      out.add(const <double>[]);
      continue;
    }
    final sounds = <double>[];
    for (final piece in one.split(RegExp(r'\s+'))) {
      final n = int.tryParse(piece);
      if (n == null || n < 0 || n > 100) return const [];
      sounds.add(n / 100.0);
    }
    out.add(sounds);
  }
  return out;
}

List<double> parseSlotScores(String row, {required int slotN}) {
  final parts = row.trim().split(RegExp(r'\s+'))
      .where((one) => one.isNotEmpty)
      .toList();
  if (parts.length != slotN) return const [];
  final out = <double>[];
  for (final one in parts) {
    if (one == '-') {
      out.add(-1);
      continue;
    }
    final n = int.tryParse(one);
    if (n == null || n < 0 || n > 100) return const [];
    out.add(n / 100.0);
  }
  return out;
}

/// How many sounds the reader made in each slot. `-` is unknown.
///
/// The two-gate score divides by the longer of this and the reference. Dropping
/// the row when it does not line up keeps a missing count from becoming a free
/// pass for an extra sound.
List<int> parseSlotSaid(String row, {required int slotN}) {
  final parts = row
      .trim()
      .split(RegExp(r'\s+'))
      .where((one) => one.isNotEmpty)
      .toList();
  if (parts.length != slotN) return const [];
  final out = <int>[];
  for (final one in parts) {
    if (one == '-') {
      out.add(-1);
      continue;
    }
    final n = int.tryParse(one);
    if (n == null || n < 0) return const [];
    out.add(n);
  }
  return out;
}


class _SpokenSlot {
  const _SpokenSlot(this.start, this.end, this.tokens, this.phone, this.share);

  final int start;
  final int end;

  /// The printed words, for the review prompt and the evidence row.
  final List<String> tokens;

  /// The sounds the native voice makes here. This is what decides the slot.
  final String phone;

  /// design/386 — required symbols per sound. Empty when the reference is older.
  final String share;
}

class _SlotBuild {
  const _SlotBuild({
    required this.slots,
    required this.code,
    required this.spanN,
    required this.posSpanN,
    required this.walkI,
    required this.pieceWeight,
    required this.remain,
  });

  final List<_SpokenSlot> slots;
  final String code;
  final int spanN;
  final int posSpanN;
  final int walkI;
  final int pieceWeight;
  final int remain;
}

_SlotBuild _spokenSlots({
  required String display,
  required String spoken,
  required List<FollowSpan> spans,
}) {
  final spanN = spans.length;
  final posSpanN = spans.where((s) => s.weight > 0 && s.end > s.start).length;
  if (display.isEmpty) {
    return _SlotBuild(
      slots: const [],
      code: 'empty_display',
      spanN: spanN,
      posSpanN: posSpanN,
      walkI: -1,
      pieceWeight: 0,
      remain: spoken.length,
    );
  }
  if (spoken.isEmpty) {
    return _SlotBuild(
      slots: const [],
      code: 'empty_spoken',
      spanN: spanN,
      posSpanN: posSpanN,
      walkI: -1,
      pieceWeight: 0,
      remain: 0,
    );
  }
  if (spans.isEmpty) {
    return _SlotBuild(
      slots: const [],
      code: 'no_spans',
      spanN: 0,
      posSpanN: 0,
      walkI: -1,
      pieceWeight: 0,
      remain: spoken.length,
    );
  }
  final scored = [
    for (final span in spans)
      if (span.weight > 0 &&
          span.start >= 0 &&
          span.end > span.start &&
          span.end <= display.length)
        span,
  ];
  if (scored.isEmpty) {
    return _SlotBuild(
      slots: const [],
      code: posSpanN == 0 ? 'weight_zero' : 'span_out_of_range',
      spanN: spanN,
      posSpanN: posSpanN,
      walkI: -1,
      pieceWeight: 0,
      remain: spoken.length,
    );
  }
  var cursor = 0;
  final out = <_SpokenSlot>[];
  for (var i = 0; i < scored.length; i++) {
    final span = scored[i];
    cursor = _skipSpokenGap(spoken, cursor);
    final end = cursor + span.weight;
    final remain = spoken.length - cursor;
    if (end > spoken.length) {
      return _SlotBuild(
        slots: const [],
        code: 'walk_past_end',
        spanN: spanN,
        posSpanN: posSpanN,
        walkI: i,
        pieceWeight: span.weight,
        remain: remain,
      );
    }
    final piece = spoken.substring(cursor, end);
    final tokens = tokenizeSkill(piece);
    cursor = end;
    if (tokens.isNotEmpty && !slotTokensScorable(tokens)) {
      // Punctuation only: consume the piece, do not open a slot for it.
      continue;
    }
    if (tokens.isEmpty) {
      return _SlotBuild(
        slots: const [],
        code: 'empty_piece',
        spanN: spanN,
        posSpanN: posSpanN,
        walkI: i,
        pieceWeight: span.weight,
        remain: spoken.length - cursor,
      );
    }
    out.add(_SpokenSlot(span.start, span.end, tokens, span.phone, span.share));
  }
  return _SlotBuild(
    slots: out,
    code: 'ok',
    spanN: spanN,
    posSpanN: posSpanN,
    walkI: scored.length,
    pieceWeight: 0,
    remain: spoken.length - cursor,
  );
}

bool _skillSpace(String text, int index) {
  final ch = text[index];
  return ch == ' ' || ch == '\n' || ch == '\t' || ch == '\r';
}

/// Same gap the length counter already skipped: spaces, then any mark that is
/// not a letter, digit, or apostrophe. A comma, period, or semicolon must not
/// become the first letters of the next slot.
final RegExp _spokenWordChar = RegExp(r"[\p{L}\p{N}']", unicode: true);

int _skipSpokenGap(String spoken, int cursor) {
  while (cursor < spoken.length && _skillSpace(spoken, cursor)) {
    cursor += 1;
  }
  while (cursor < spoken.length &&
      !_spokenWordChar.hasMatch(spoken[cursor])) {
    cursor += 1;
    while (cursor < spoken.length && _skillSpace(spoken, cursor)) {
      cursor += 1;
    }
  }
  return cursor;
}

final RegExp _phoneStress = RegExp("[ˈˌ.ːˑ]");

final RegExp _slotHasSound = RegExp(r'[\p{L}\p{N}]', unicode: true);

bool slotTokensScorable(List<String> tokens) =>
    tokens.any((token) => _slotHasSound.hasMatch(token));

// design/370 - the whole design/365 word fold lived here: spelling pairs
// (vapour/vapor), element symbols read as names (Ni -> nickel), digit-letter
// splits (2p -> 2, p), possessive marks, number words, their/there/they're,
// and the plural tolerance. Every one of them existed to forgive the
// orthography a recognizer happened to type. A sound has no orthography, so
// all of it is gone with the transcript. See design/365 for what it did.

/// One sound per item.
///
/// eSpeak writes a whole word as one run (`dɪspˈɜːʃən`) while the waveform model
/// writes one sound at a time. Comparing the two needs both sides cut the same
/// way, so a run is opened at every base letter and the marks that belong to it
/// are carried along.
List<String> phoneUnits(String ipa) {
  final units = <String>[];
  var tied = false;
  for (final ch in ipa.replaceAll(_phoneStress, '').split('')) {
    if (ch.trim().isEmpty) {
      tied = false;
      continue;
    }
    if (_phoneTie.contains(ch)) {
      if (units.isNotEmpty) {
        units[units.length - 1] += ch;
        tied = true;
      }
      continue;
    }
    if (_phoneMark.hasMatch(ch)) {
      if (units.isNotEmpty) units[units.length - 1] += ch;
      continue;
    }
    if (tied && units.isNotEmpty) {
      units[units.length - 1] += ch;
      tied = false;
      continue;
    }
    units.add(ch);
  }
  return units;
}

const String _phoneTie = '\u0361\u035c\u200d';
final RegExp _phoneMark =
    RegExp(r'[\u0300-\u036f\u1dc0-\u1dff\u20d0-\u20f0ʰʲʷⁿˠˤ]', unicode: true);

List<String> _phonePieces(String ipa) => phoneUnits(ipa);

/// Symbols the waveform model can never write, so a reference carrying one was
/// not read by it. design/373.
///
/// The model reads sounds out of audio, and its whole vocabulary is 392 tokens
/// with no stress marks and no ties -- it holds `eɪ` as a single token and
/// never writes `ˈ` at all. eSpeak, which design/368 cut out, wrote both,
/// because it was reading a spelling out of a dictionary. So a cached row
/// holding one of these is a reading by the voice the scorer no longer compares
/// against, and no take, however good, can match it.
bool soundsFromOtherReader(String phone) => _otherReader.hasMatch(phone);

/// design/388 — sounds with no native spread beside them. A design/386 share
/// is bare symbols, and anything older has none; a spread always holds `=`.
bool spreadMissing(String phone, String share) =>
    phone.trim().isNotEmpty && !share.contains('=');

final RegExp _otherReader =
    RegExp(r'[\u02c8\u02cc\u200d\u0361\u035c]', unicode: true);

/// No slot carried a reference sound, so the take cannot be judged. design/370.
const String kSoundRefMissing = 'sound_ref_missing';

/// Every slot's reference was too short to tell words apart. design/371.
const String kSoundTooShort = 'sound_too_short';

/// Least overlap that counts as the same sound. See design/366 for the sweep.
const double kPhoneOverlapMin = 0.72;

/// design/388 — the lowest line [phoneOverlap] is judged by. That is the
/// design/371 word overlap the phone falls back on when the server sent no
/// sound rows, and design/375 measured its own line: 0.747 − 0.75 × 0.230. The
/// account line is in spread-overlap units now and sits lower, which on this
/// ruler would pass words that were not read.
const double kWordOverlapLine = 0.57;

/// Below this a target matches almost anything, so it is not judged by sound.
const int kPhoneMinUnits = 3;

/// design/388 — stage one, then stage two.
///
/// Stage one asks about every native symbol at or above the bar, (20 + rung)%.
/// When there is at least one and the reader has every one of them at the bar
/// too, the sound passes. Otherwise — no native symbol that high, or the reader
/// short on one — the sound's [overlap] is compared with the account line.
bool soundClears(
  double overlap, {
  List<SoundTop> top = const [],
  required double bar,
  required double line,
}) {
  const eps = 1e-9;
  final need = [
    for (final one in top)
      if (one.native >= bar - eps) one,
  ];
  if (need.isNotEmpty && need.every((one) => one.reader >= bar - eps)) {
    return true;
  }
  return overlap >= line;
}

/// Word score after that sound rule, over the longer of the two sides.
///
/// Null when the overlap row does not line up with the sounds, or the
/// said-count is missing. The caller keeps the server's own score then.
/// [tops] that do not line up are dropped, which leaves every sound to the line.
double? twoGateWordScore({
  required List<double> probs,
  List<List<SoundTop>> tops = const [],
  required int soundN,
  required int said,
  required double bar,
  required double line,
}) {
  if (soundN <= 0 || probs.length != soundN || said < 0) return null;
  final lined = tops.length == soundN;
  var matches = 0;
  for (var i = 0; i < soundN; i++) {
    if (soundClears(
      probs[i],
      top: lined ? tops[i] : const [],
      bar: bar,
      line: line,
    )) {
      matches += 1;
    }
  }
  final denom = soundN > said ? soundN : said;
  return matches / denom;
}

/// design/388 — the server's `slot_top` row: words barred, sounds comma
/// separated, `native:reader` percents spaced.
///
/// `-` is a word with nothing to send and comes back empty. A row whose word
/// count does not match, or holding anything that is not a pair of percents,
/// is refused whole, like [parseSlotSounds].
List<List<List<SoundTop>>> parseSlotTops(String row, {required int slotN}) {
  final parts = row.trim().split('|');
  if (row.trim().isEmpty || parts.length != slotN) return const [];
  final out = <List<List<SoundTop>>>[];
  for (final part in parts) {
    final one = part.trim();
    if (one == '-') {
      out.add(const <List<SoundTop>>[]);
      continue;
    }
    final sounds = <List<SoundTop>>[];
    for (final sound in part.split(',')) {
      final pairs = <SoundTop>[];
      for (final piece in sound.trim().split(RegExp(r'\s+'))) {
        if (piece.isEmpty) continue;
        final halves = piece.split(':');
        if (halves.length != 2) return const [];
        final a = int.tryParse(halves[0]);
        final b = int.tryParse(halves[1]);
        if (a == null || b == null || a < 0 || a > 100 || b < 0 || b > 100) {
          return const [];
        }
        pairs.add(SoundTop(a / 100.0, b / 100.0));
      }
      sounds.add(pairs);
    }
    out.add(sounds);
  }
  return out;
}

/// True when [target] is heard anywhere in [heardWords].
///
/// design/366 — the waveform model returns one run of sounds for the whole take.
/// Comparing a word against its own cut of that run assumed eSpeak and the model
/// emit the same number of sounds per word. They do not, so the cut drifted
/// further out of step with every word and a late word was compared against the
/// wrong stretch. Walking the run instead lifted the pass rate on reads the
/// words had already confirmed from 8% to 32% at this same threshold.
/// design/375 — [line] is the caller's, because the review has to pass on the
/// same ground the speak phase does. Left to itself it uses the cold line rather
/// than design/366's 0.72, which answers how close two different words may sound
/// and is a stricter bar than any reading is judged by. design/388 — never
/// under [kWordOverlapLine], the line this ruler was measured with.
bool phonesClose(
  String target,
  List<String> heardWords, {
  double line = kWordOverlapLine,
}) =>
    phoneOverlap(target, heardWords) >= math.max(line, kWordOverlapLine);

/// How much of [target] is heard in [heardWords], or -1 when it cannot be asked.
///
/// design/371 - the pass line is no longer a constant, so the caller needs the
/// number and not just the verdict. -1 means the question cannot be put at all,
/// which happens only when the reference is too short to tell words apart. A
/// take with nothing in it scores 0, because 0 is a real answer: none of the
/// sounds were there.
double phoneOverlap(String target, List<String> heardWords) {
  final left = _phonePieces(target);
  if (left.length < kPhoneMinUnits) return -1;
  final flat = <String>[];
  for (final heard in heardWords) {
    flat.addAll(_phonePieces(heard));
  }
  return bestWindowOverlap(left, flat);
}

/// Best overlap of [left] against any stretch of [flat].
///
/// The stretch is tried one sound short through two sounds long: the model drops
/// a sound less often than it splits one in two.
double bestWindowOverlap(List<String> left, List<String> flat) {
  final span = left.length;
  final starts = flat.length - span + 1;
  var best = 0.0;
  for (var start = 0; start < (starts < 1 ? 1 : starts); start++) {
    for (var width = span - 1; width <= span + 2; width++) {
      if (width < 1) continue;
      final end = start + width;
      final right = flat.sublist(start, end > flat.length ? flat.length : end);
      if (right.isEmpty) continue;
      final got = _overlap(left, right);
      if (got > best) best = got;
    }
  }
  return best;
}

double _overlap(List<String> left, List<String> right) {
  final rows = left.length + 1;
  final cols = right.length + 1;
  final dist = List.generate(rows, (_) => List.filled(cols, 0));
  for (var i = 0; i < rows; i++) {
    dist[i][0] = i;
  }
  for (var j = 0; j < cols; j++) {
    dist[0][j] = j;
  }
  for (var i = 1; i < rows; i++) {
    for (var j = 1; j < cols; j++) {
      final cost = left[i - 1] == right[j - 1] ? 0 : 1;
      final del = dist[i - 1][j] + 1;
      final ins = dist[i][j - 1] + 1;
      final sub = dist[i - 1][j - 1] + cost;
      dist[i][j] = del < ins ? (del < sub ? del : sub) : (ins < sub ? ins : sub);
    }
  }
  final longest = left.length > right.length ? left.length : right.length;
  return 1 - (dist[rows - 1][cols - 1] / longest);
}
