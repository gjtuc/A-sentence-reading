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
  const MissedWordSpan(this.start, this.end);

  final int start;
  final int end;
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

/// One printed word is one score slot, including function words.
///
/// A printed token spoken as several pieces (`CVD` → `c v d`, `Pt` →
/// `platinum`) is still one slot. Any missing piece fails the whole slot.
SkillScoreResult spokenSlotCoverage({
  required String display,
  required String spoken,
  required List<FollowSpan> spans,
  required String? heard,
}) {
  final slots = _spokenSlots(display: display, spoken: spoken, spans: spans);
  if (slots.isEmpty) {
    return const SkillScoreResult(
      ok: false,
      error: 'empty_slot_ref',
      listV: kSpokenSlotListV,
    );
  }
  final have = <String, int>{};
  for (final token in tokenizeSkill(heard)) {
    have[token] = (have[token] ?? 0) + 1;
  }
  var hit = 0;
  final missed = <MissedWordSpan>[];
  for (final slot in slots) {
    if (_takeSpokenSlot(slot.tokens, have)) {
      hit += 1;
    } else {
      missed.add(MissedWordSpan(slot.start, slot.end));
    }
  }
  final acc = hit / slots.length;
  return SkillScoreResult(
    ok: true,
    accuracy: (acc * 10000).round() / 10000.0,
    refN: slots.length,
    hitN: hit,
    listV: kSpokenSlotListV,
    missedSpans: missed,
  );
}

class _SpokenSlot {
  const _SpokenSlot(this.start, this.end, this.tokens);

  final int start;
  final int end;
  final List<String> tokens;
}

List<_SpokenSlot> _spokenSlots({
  required String display,
  required String spoken,
  required List<FollowSpan> spans,
}) {
  if (display.isEmpty || spoken.isEmpty) return const [];
  final scored = [
    for (final span in spans)
      if (span.weight > 0 &&
          span.start >= 0 &&
          span.end > span.start &&
          span.end <= display.length)
        span,
  ];
  if (scored.isEmpty) return const [];
  var cursor = 0;
  final out = <_SpokenSlot>[];
  for (final span in scored) {
    while (cursor < spoken.length && _skillSpace(spoken, cursor)) {
      cursor += 1;
    }
    final end = cursor + span.weight;
    if (end > spoken.length) return const [];
    final tokens = tokenizeSkill(spoken.substring(cursor, end));
    cursor = end;
    if (tokens.isEmpty) return const [];
    out.add(_SpokenSlot(span.start, span.end, tokens));
  }
  return out;
}

bool _skillSpace(String text, int index) {
  final ch = text[index];
  return ch == ' ' || ch == '\n' || ch == '\t' || ch == '\r';
}

/// Every spoken piece must be heard. Pieces that were heard stay consumed.
bool _takeSpokenSlot(List<String> tokens, Map<String, int> have) {
  var ok = true;
  for (final token in tokens) {
    final left = have[token] ?? 0;
    if (left <= 0) {
      ok = false;
      continue;
    }
    if (left == 1) {
      have.remove(token);
    } else {
      have[token] = left - 1;
    }
  }
  return ok;
}
