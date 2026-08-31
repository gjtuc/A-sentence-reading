/// design/28 · 124 — body Fig./Scheme/Table → carousel figure index.
/// design/152 — slot_key fallback + bare S2 when supplementary merged.
/// design/164 — Figure 6C / 6(C) → base Figure 6 chip.
library;

final _kindNumLower = RegExp(
  r'\b((?:Figures?|Figs?|Scheme|Table)\.?\s*(S?\d+[a-z]))\b',
  caseSensitive: true,
);
final _kindNumBase = RegExp(
  r'\b((?:Figures?|Figs?|Scheme|Table)\.?\s*(S?\d+))\b',
  caseSensitive: false,
);
final _kindPanel = RegExp(
  r'\b((?:Figures?|Figs?|Scheme|Table)\.?\s*(S?\d+)\s*(?:\(([A-Za-z])\)|([A-Z])))\b',
  caseSensitive: false,
);
final _bareS = RegExp(r'\b(S\d+[a-z]?)\b', caseSensitive: false);
final _tag = RegExp(r'<[^>]+>');

String stripTags(String? html) => (html ?? '').replaceAll(_tag, ' ');

String _kindToken(String kindRaw) {
  final k = kindRaw.toLowerCase();
  if (k.startsWith('fig')) return 'fig';
  if (k.startsWith('scheme')) return 'scheme';
  return 'table';
}

String? _baseKeyFromNum(String kind, String num) {
  final lower = num.toLowerCase();
  if (lower.startsWith('s')) {
    final m = RegExp(r'^s(\d+)', caseSensitive: false).firstMatch(lower);
    if (m == null) return null;
    return '$kind:s${int.parse(m.group(1)!)}';
  }
  final m = RegExp(r'^(\d+)').firstMatch(lower);
  if (m == null) return null;
  return '$kind:${int.parse(m.group(1)!)}';
}

String _baseDisplayLabel(String kindRaw, String num) {
  final k = kindRaw.toLowerCase();
  if (k.startsWith('fig')) return 'Figure $num';
  if (k.startsWith('scheme')) return 'Scheme $num';
  return 'Table $num';
}

String? _normKey(String raw) {
  final m = RegExp(
    r'(Figures?|Figs?|Scheme|Table)\.?\s*(S?\d+(?:[a-z])?)',
    caseSensitive: true,
  ).firstMatch(raw);
  if (m == null) {
    final m2 = RegExp(
      r'(Figures?|Figs?|Scheme|Table)\.?\s*(S?\d+)',
      caseSensitive: false,
    ).firstMatch(raw);
    if (m2 == null) return null;
    final kind = _kindToken(m2.group(1)!);
    final num = m2.group(2)!.toLowerCase();
    return '$kind:$num';
  }
  final kind = _kindToken(m.group(1)!);
  final num = m.group(2)!.toLowerCase();
  return '$kind:$num';
}

({String label, String key})? _panelParse(RegExpMatch m) {
  final full = m.group(1)!;
  final inner = RegExp(
    r'(Figures?|Figs?|Scheme|Table)\.?\s*(S?\d+)\s*(?:\(([A-Za-z])\)|([A-Z]))',
    caseSensitive: false,
  ).firstMatch(full);
  if (inner == null) return null;
  final upper = inner.group(4);
  if (upper != null && upper != upper.toUpperCase()) return null;
  final kindRaw = inner.group(1)!;
  final num = inner.group(2)!;
  final kind = _kindToken(kindRaw);
  final baseKey = _baseKeyFromNum(kind, num);
  if (baseKey == null) return null;
  return (label: _baseDisplayLabel(kindRaw, num), key: baseKey);
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

({String label, String key})? _panelLabelAndKey(String raw) {
  final m = _kindPanel.firstMatch(raw);
  if (m == null) return null;
  return _panelParse(m);
}

List<String> _matchKeysForLabel(
  String refLabel, {
  bool supplementaryMerged = false,
}) {
  final keys = <String>[];
  final panel = _panelLabelAndKey(refLabel);
  if (panel != null && !keys.contains(panel.key)) {
    keys.add(panel.key);
  }
  final exact = _wantKey(refLabel, supplementaryMerged: supplementaryMerged);
  if (exact != null && !keys.contains(exact)) {
    keys.add(exact);
    final parts = exact.split(':');
    if (parts.length == 2) {
      final base = _baseKeyFromNum(parts[0], parts[1]);
      if (base != null && base != exact && !keys.contains(base)) {
        keys.add(base);
      }
    }
  }
  return keys;
}

/// Body refs in appearance order (deduped by match key).
List<String> parseFigRefs(String? text, {bool supplementaryMerged = false}) {
  final plain = stripTags(text);
  final hits = <({int start, String label, String key})>[];
  for (final m in _kindNumLower.allMatches(plain)) {
    final label = m.group(1)!.replaceAll(RegExp(r'\s+'), ' ').trim();
    final key = _wantKey(label, supplementaryMerged: supplementaryMerged);
    if (key == null) continue;
    hits.add((start: m.start, label: label, key: key));
  }
  for (final m in _kindNumBase.allMatches(plain)) {
    if (m.end < plain.length && RegExp(r'[A-Za-z]').hasMatch(plain[m.end])) {
      continue;
    }
    final label = m.group(1)!.replaceAll(RegExp(r'\s+'), ' ').trim();
    final key = _wantKey(label, supplementaryMerged: supplementaryMerged);
    if (key == null) continue;
    hits.add((start: m.start, label: label, key: key));
  }
  for (final m in _kindPanel.allMatches(plain)) {
    final parsed = _panelParse(m);
    if (parsed == null) continue;
    hits.add((start: m.start, label: parsed.label, key: parsed.key));
  }
  hits.sort((a, b) => a.start.compareTo(b.start));
  final out = <String>[];
  final seen = <String>{};
  for (final h in hits) {
    if (!seen.add(h.key)) continue;
    out.add(h.label);
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
  final slice = head.length > 80 ? head.substring(0, 80) : head;
  RegExpMatch? m = _kindNumLower.firstMatch(head) ?? _kindNumLower.firstMatch(slice);
  m ??= _kindNumBase.firstMatch(head) ?? _kindNumBase.firstMatch(slice);
  if (m == null) return null;
  return _normKey(m.group(1)!);
}

int? _indexForKey({
  required String want,
  required List<String> captions,
  required List<String> slotKeys,
}) {
  final wantSlot = want.replaceFirst('scheme:', 'fig:');
  for (var i = 0; i < captions.length; i++) {
    if (i < slotKeys.length) {
      final sk = slotKeys[i].trim().toLowerCase();
      if (sk.isNotEmpty && sk == wantSlot) return i;
    }
    final capKey = captionFigKey(captions[i]);
    if (capKey == want) return i;
    if (capKey != null) {
      final parts = capKey.split(':');
      if (parts.length == 2) {
        final base = _baseKeyFromNum(parts[0], parts[1]);
        if (base == want) return i;
      }
    }
  }
  return null;
}

/// Match [refLabel] to figures by slot_key then caption key. Null if none.
int? matchFigureIndex({
  required String refLabel,
  required List<String> captions,
  List<String> slotKeys = const [],
  bool supplementaryMerged = false,
}) {
  for (final want in _matchKeysForLabel(
    refLabel,
    supplementaryMerged: supplementaryMerged,
  )) {
    final idx = _indexForKey(
      want: want,
      captions: captions,
      slotKeys: slotKeys,
    );
    if (idx != null) return idx;
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
  final seenIdx = <int>{};
  for (final label in parseFigRefs(text, supplementaryMerged: supplementaryMerged)) {
    final idx = matchFigureIndex(
      refLabel: label,
      captions: captions,
      slotKeys: slotKeys,
      supplementaryMerged: supplementaryMerged,
    );
    if (idx == null || !seenIdx.add(idx)) continue;
    rows.add(FigRefHint(ref: label, figureIndex: idx));
  }
  return rows;
}
