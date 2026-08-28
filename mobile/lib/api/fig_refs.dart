/// design/28 · 124 — body Fig./Scheme/Table → carousel figure index.
/// design/152 — slot_key fallback + bare S2 when supplementary merged.
library;

final _kindNum = RegExp(
  r'\b((?:Figures?|Figs?|Scheme|Table)\.?\s*(S?\d+[a-z]?))\b',
  caseSensitive: false,
);
final _bareS = RegExp(r'\b(S\d+[a-z]?)\b', caseSensitive: false);
final _tag = RegExp(r'<[^>]+>');

String stripTags(String? html) => (html ?? '').replaceAll(_tag, ' ');

String? _normKey(String raw) {
  final m = RegExp(
    r'(Figures?|Figs?|Scheme|Table)\.?\s*(S?\d+[a-z]?)',
    caseSensitive: false,
  ).firstMatch(raw);
  if (m == null) return null;
  final kindRaw = m.group(1)!.toLowerCase();
  final num = m.group(2)!.toLowerCase();
  final String kind;
  if (kindRaw.startsWith('fig')) {
    kind = 'fig';
  } else if (kindRaw.startsWith('scheme')) {
    kind = 'scheme';
  } else {
    kind = 'table';
  }
  return '$kind:$num';
}

String? _wantKey(String raw, {bool supplementaryMerged = false}) {
  final want = _normKey(raw);
  if (want != null) return want;
  if (supplementaryMerged) {
    final m = RegExp(r'^S(\d+[a-z]?)$', caseSensitive: false).firstMatch(raw.trim());
    if (m != null) return 'fig:s${m.group(1)!.toLowerCase()}';
  }
  return null;
}

/// Body refs in appearance order (deduped).
List<String> parseFigRefs(String? text, {bool supplementaryMerged = false}) {
  final plain = stripTags(text);
  final out = <String>[];
  final seen = <String>{};
  for (final m in _kindNum.allMatches(plain)) {
    final label = m.group(1)!.replaceAll(RegExp(r'\s+'), ' ').trim();
    final key = _wantKey(label, supplementaryMerged: supplementaryMerged);
    if (key == null || !seen.add(key)) continue;
    out.add(label);
  }
  if (supplementaryMerged) {
    for (final m in _bareS.allMatches(plain)) {
      final label = m.group(1)!;
      final key = _wantKey(label, supplementaryMerged: true);
      if (key == null || !seen.add(key)) continue;
      out.add(label);
    }
  }
  return out;
}

String? captionFigKey(String? caption) {
  final head = stripTags(caption).trim();
  if (head.isEmpty) return null;
  final m = _kindNum.firstMatch(head) ??
      _kindNum.firstMatch(head.length > 80 ? head.substring(0, 80) : head);
  if (m == null) return null;
  return _normKey(m.group(1)!);
}

/// Match [refLabel] to figures by slot_key then caption key. Null if none.
int? matchFigureIndex({
  required String refLabel,
  required List<String> captions,
  List<String> slotKeys = const [],
  bool supplementaryMerged = false,
}) {
  final want = _wantKey(refLabel, supplementaryMerged: supplementaryMerged);
  if (want == null) return null;
  final wantSlot = want.replaceFirst('scheme:', 'fig:');
  for (var i = 0; i < captions.length; i++) {
    if (i < slotKeys.length) {
      final sk = slotKeys[i].trim().toLowerCase();
      if (sk.isNotEmpty && sk == wantSlot) return i;
    }
    if (captionFigKey(captions[i]) == want) return i;
  }
  return null;
}

class FigRefHint {
  const FigRefHint({required this.ref, required this.figureIndex});

  final String ref;
  final int figureIndex;
}

/// Only matched refs (design/28 — no chip when unmatched).
List<FigRefHint> hintsForSentence({
  required String? text,
  required List<String> captions,
  List<String> slotKeys = const [],
  bool supplementaryMerged = false,
}) {
  final rows = <FigRefHint>[];
  for (final label in parseFigRefs(text, supplementaryMerged: supplementaryMerged)) {
    final idx = matchFigureIndex(
      refLabel: label,
      captions: captions,
      slotKeys: slotKeys,
      supplementaryMerged: supplementaryMerged,
    );
    if (idx == null) continue;
    rows.add(FigRefHint(ref: label, figureIndex: idx));
  }
  return rows;
}
