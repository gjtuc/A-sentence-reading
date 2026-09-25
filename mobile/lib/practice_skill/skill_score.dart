/// design/212 — content-word multiset coverage (mirrors practice_skill_score.py).
library;

import '../practice_rhythm/follow_span.dart';

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

SkillScoreResult contentWordCoverage(String? expectedSpoken, String? heard) {
  final ref = contentWords(expectedSpoken);
  final hyp = contentWords(heard);
  if (ref.isEmpty) {
    return const SkillScoreResult(
      ok: false,
      error: 'empty_content_ref',
    );
  }
  final need = <String, int>{};
  for (final w in ref) {
    need[w] = (need[w] ?? 0) + 1;
  }
  final have = <String, int>{};
  for (final w in hyp) {
    have[w] = (have[w] ?? 0) + 1;
  }
  var hit = 0;
  for (final e in need.entries) {
    final h = have[e.key] ?? 0;
    hit += h < e.value ? h : e.value;
  }
  final acc = hit / ref.length;
  return SkillScoreResult(
    ok: true,
    accuracy: (acc * 10000).round() / 10000.0,
    refN: ref.length,
    hitN: hit,
  );
}

/// Content words in [display] that the heard take did not cover.
/// Same bag as [contentWordCoverage]. Function words are not marked.
List<MissedWordSpan> missedContentSpans({
  required String display,
  required String? expectedSpoken,
  required String? heard,
}) {
  final ref = contentWords(expectedSpoken);
  final hyp = contentWords(heard);
  if (ref.isEmpty || display.isEmpty) return const [];
  final missed = <String, int>{};
  for (final w in ref) {
    missed[w] = (missed[w] ?? 0) + 1;
  }
  for (final w in hyp) {
    final left = missed[w] ?? 0;
    if (left <= 0) continue;
    if (left == 1) {
      missed.remove(w);
    } else {
      missed[w] = left - 1;
    }
  }
  if (missed.isEmpty) return const [];
  final spans = <MissedWordSpan>[];
  final word = RegExp(r"[A-Za-z0-9]+(?:'[A-Za-z]+)?", unicode: true);
  for (final m in word.allMatches(display)) {
    final key = normalizeSkillText(m.group(0));
    if (key.isEmpty || kFunctionWords.contains(key)) continue;
    final left = missed[key] ?? 0;
    if (left <= 0) continue;
    spans.add(MissedWordSpan(m.start, m.end));
    if (left == 1) {
      missed.remove(key);
    } else {
      missed[key] = left - 1;
    }
    if (missed.isEmpty) break;
  }
  return spans;
}

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
}

/// One printed word is one score slot, including function words.
///
/// A printed token spoken as several pieces (`CVD` → `c v d`, `Pt` →
/// `platinum`) is still one slot. Any missing piece fails the whole slot.
SpokenSlotDiag diagnoseSpokenSlots({
  required String display,
  required String spoken,
  required List<FollowSpan> spans,
  required String? heard,
  List<String> heardPhones = const [],
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
  final have = <String, int>{};
  for (final token in tokenizeSkill(canonicalizeSoundAlikes(heard))) {
    have[token] = (have[token] ?? 0) + 1;
  }
  final heardPhoneWords = _sliceHeardPhones(built.slots, heardPhones);
  var hit = 0;
  var soundPassN = 0;
  final missed = <MissedWordSpan>[];
  final marks = StringBuffer();
  final pieces = <String>[];
  for (final slot in built.slots) {
    final lexical = _takeSpokenSlot(slot.tokens, have);
    final bySound = !lexical && phonesClose(slot.phone, heardPhoneWords);
    if (bySound) soundPassN += 1;
    final ok = lexical || bySound;
    marks.write(ok ? '1' : '0');
    pieces.add(slot.tokens.join(' '));
    if (ok) {
      hit += 1;
    } else {
      missed.add(MissedWordSpan(
        slot.start,
        slot.end,
        spoken: slot.tokens.join(' '),
        phone: slot.phone,
      ));
    }
  }
  final acc = hit / built.slots.length;
  return SpokenSlotDiag(
    score: SkillScoreResult(
      ok: true,
      accuracy: (acc * 10000).round() / 10000.0,
      refN: built.slots.length,
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
  );
}

/// Score only. Diagnostics live on [diagnoseSpokenSlots].
SkillScoreResult spokenSlotCoverage({
  required String display,
  required String spoken,
  required List<FollowSpan> spans,
  required String? heard,
}) {
  return diagnoseSpokenSlots(
    display: display,
    spoken: spoken,
    spans: spans,
    heard: heard,
  ).score;
}

class _SpokenSlot {
  const _SpokenSlot(this.start, this.end, this.tokens, this.phone);

  final int start;
  final int end;
  final List<String> tokens;
  final String phone;
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
    final tokens = tokenizeSkill(spoken.substring(cursor, end));
    cursor = end;
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
    out.add(_SpokenSlot(span.start, span.end, tokens, span.phone));
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
final RegExp _oneLetter = RegExp(r'^\p{L}$', unicode: true);

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

/// Every spoken piece must be heard. Pieces that were heard stay consumed.
bool _takeSpokenSlot(List<String> tokens, Map<String, int> have) {
  if (tokens.length >= 2 &&
      tokens.every((token) => token.length == 1 && _oneLetter.hasMatch(token))) {
    final joined = tokens.join();
    final left = have[joined] ?? 0;
    if (left > 0) {
      if (left == 1) {
        have.remove(joined);
      } else {
        have[joined] = left - 1;
      }
      return true;
    }
  }
  var ok = true;
  for (final token in tokens) {
    if (takeSkillToken(token, have) == 0) ok = false;
  }
  return ok;
}

final RegExp _theirPhrase = RegExp(
  r"\bthey(?:'re| are)\b",
  caseSensitive: false,
);
const Set<String> _theirWords = {'their', 'there', "they're"};
final RegExp _phoneStress = RegExp("[ˈˌ.ːˑ]");

List<String> _sliceHeardPhones(List<_SpokenSlot> slots, List<String> heardPhones) {
  final cleaned = [
    for (final phone in heardPhones) phone.trim(),
  ].where((phone) => phone.isNotEmpty).toList();
  if (cleaned.length != 1 || slots.length <= 1) return cleaned;
  final flat = _phonePieces(cleaned.single);
  if (flat.length < 2) return cleaned;
  var index = 0;
  final out = <String>[];
  for (final slot in slots) {
    final count = _phonePieces(slot.phone).length;
    if (count <= 0 || index >= flat.length) {
      out.add('');
      continue;
    }
    final end = index + count > flat.length ? flat.length : index + count;
    out.add(flat.sublist(index, end).join(' '));
    index = end;
  }
  return out;
}

String canonicalizeSoundAlikes(String? text) {
  var folded = (text ?? '').replaceAll(_theirPhrase, 'their');
  return folded.split(RegExp(r'\s+')).map((token) {
    final key = token.replaceAll(RegExp(r"""[.,;:!?"']"""), '').toLowerCase();
    if (_theirWords.contains(key)) return 'their';
    final digit = kNumberWordDigits[key];
    if (digit != null) return digit;
    return token;
  }).join(' ');
}

/// A printed `1` is read and heard as `one`, so both sides fold to the digit.
/// Compounds are folded token by token, which is enough for the numbers a paper
/// spells out beside a unit.
const Map<String, String> kNumberWordDigits = {
  'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4',
  'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9',
  'ten': '10', 'eleven': '11', 'twelve': '12', 'thirteen': '13',
  'fourteen': '14', 'fifteen': '15', 'sixteen': '16', 'seventeen': '17',
  'eighteen': '18', 'nineteen': '19', 'twenty': '20', 'thirty': '30',
  'forty': '40', 'fifty': '50', 'sixty': '60', 'seventy': '70',
  'eighty': '80', 'ninety': '90',
};

/// The same word with or without a trailing `s`. `1 nm` is read as
/// `nanometers` while a speaker says `nanometer`, and neither is a mistake.
int takeSkillToken(String token, Map<String, int> have) {
  for (final form in _tokenForms(token)) {
    final left = have[form] ?? 0;
    if (left <= 0) continue;
    if (left == 1) {
      have.remove(form);
    } else {
      have[form] = left - 1;
    }
    return 1;
  }
  return 0;
}

List<String> _tokenForms(String token) {
  if (token.length < 3) return [token];
  if (token.endsWith('s')) {
    return [token, token.substring(0, token.length - 1)];
  }
  return [token, '${token}s'];
}

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

bool phonesClose(String target, List<String> heardWords) {
  final left = _phonePieces(target);
  if (left.length < 3) return false;
  for (final heard in heardWords) {
    final right = _phonePieces(heard);
    if (right.isEmpty) continue;
    if (_overlap(left, right) >= 0.72) return true;
  }
  return false;
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
