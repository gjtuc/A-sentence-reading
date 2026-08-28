/// design/41 · 148 — body cite numbers ↔ References bibliography.
library;

final _tag = RegExp(r'<[^>]+>');
final _bracket = RegExp(
  r'\[(\d+(?:\s*[-–—,]\s*\d+)*(?:\s*,\s*\d+(?:\s*[-–—,]\s*\d+)*)*)\]',
);
final _supNum = RegExp(r'<sup>\s*(\d{1,3})\s*</sup>', caseSensitive: false);
final _dollarTexCite = RegExp(
  r'\$\{\^(\d+(?:\s*[,–—-]\s*\d+)*)\}\$|\$\^\{(\d+(?:\s*[,–—-]\s*\d+)*)\}\$',
  caseSensitive: false,
);
final _dollarCite = RegExp(r'(?<=[A-Za-z)\]])\$(\d{1,3})(?!\d)');

String stripTags(String? html) => (html ?? '').replaceAll(_tag, ' ');

List<int> _expandToken(String token) {
  final out = <int>[];
  final seen = <int>{};
  for (final part in token.split(RegExp(r'\s*,\s*'))) {
    final p = part.trim();
    if (p.isEmpty) continue;
    final range = RegExp(r'^(\d+)\s*[-–—]\s*(\d+)$').firstMatch(p);
    if (range != null) {
      final a = int.parse(range.group(1)!);
      final b = int.parse(range.group(2)!);
      if (a > b || b - a > 40) continue;
      for (var n = a; n <= b; n++) {
        if (!seen.contains(n) && n >= 1 && n <= 9999) {
          seen.add(n);
          out.add(n);
        }
      }
      continue;
    }
    if (RegExp(r'^\d+$').hasMatch(p)) {
      final n = int.parse(p);
      if (!seen.contains(n) && n >= 1 && n <= 9999) {
        seen.add(n);
        out.add(n);
      }
    }
  }
  return out;
}

/// Citation numbers in appearance order (deduped).
List<int> parseCiteNumbers(String? text) {
  final raw = text ?? '';
  final out = <int>[];
  final seen = <int>{};

  void addAll(List<int> nums) {
    for (final n in nums) {
      if (!seen.contains(n)) {
        seen.add(n);
        out.add(n);
      }
    }
  }

  final plain = stripTags(raw);
  for (final m in _bracket.allMatches(plain)) {
    addAll(_expandToken(m.group(1)!));
  }
  for (final m in _supNum.allMatches(raw)) {
    addAll([int.parse(m.group(1)!)]);
  }
  addAll(_parseDollarCiteNumbers(raw));
  return out;
}

List<int> _parseDollarCiteNumbers(String raw) {
  final out = <int>[];
  final seen = <int>{};
  for (final m in _dollarTexCite.allMatches(raw)) {
    final inner = m.group(1) ?? m.group(2) ?? '';
    for (final n in _expandToken(inner.replaceAll(' ', ''))) {
      if (!seen.contains(n)) {
        seen.add(n);
        out.add(n);
      }
    }
  }
  for (final m in _dollarCite.allMatches(raw)) {
    final n = int.parse(m.group(1)!);
    if (!seen.contains(n) && n >= 1 && n <= 999) {
      seen.add(n);
      out.add(n);
    }
  }
  return out;
}

/// design/49 — display-only strip; parsing uses raw [text].
String stripCiteMarkersForDisplay(String? html) {
  var s = html ?? '';
  s = s.replaceAllMapped(_supNum, (m) {
    final v = int.tryParse(m.group(1) ?? '');
    return (v != null && v >= 1 && v <= 999) ? '' : m.group(0)!;
  });
  s = s.replaceAllMapped(_bracket, (m) {
    return _expandToken(m.group(1)!).isNotEmpty ? '' : m.group(0)!;
  });
  s = s.replaceAllMapped(_dollarTexCite, (m) {
    final inner = m.group(1) ?? m.group(2) ?? '';
    return _expandToken(inner.replaceAll(' ', '')).isNotEmpty ? '' : m.group(0)!;
  });
  s = s.replaceAllMapped(_dollarCite, (m) {
    final v = int.tryParse(m.group(1) ?? '');
    return (v != null && v >= 1 && v <= 999) ? '' : m.group(0)!;
  });
  s = s.replaceAll(RegExp(r'\s+([.,;:!?)])'), r'$1');
  s = s.replaceAll(RegExp(r'\s{2,}'), ' ');
  return s.trim();
}

/// One References row matched to a cite number.
class CiteRefEntry {
  const CiteRefEntry({
    required this.n,
    required this.text,
    this.doi = '',
  });

  final int n;
  final String text;
  final String doi;
}

CiteRefEntry? lookupReference(int n, List<CiteRefEntry> bibliography) {
  for (final e in bibliography) {
    if (e.n == n && e.text.trim().isNotEmpty) return e;
  }
  return null;
}

/// Matched bibliography rows for [text] (order follows cite numbers in text).
List<CiteRefEntry> hintsForSentence({
  required String? text,
  required List<CiteRefEntry> bibliography,
}) {
  final rows = <CiteRefEntry>[];
  for (final n in parseCiteNumbers(text)) {
    final hit = lookupReference(n, bibliography);
    if (hit != null) rows.add(hit);
  }
  return rows;
}

List<CiteRefEntry> parseReferenceList(Object? raw) {
  if (raw is! List) return [];
  final out = <CiteRefEntry>[];
  final seen = <int>{};
  for (final item in raw) {
    if (item is! Map) continue;
    final map = Map<String, dynamic>.from(item);
    final n = int.tryParse('${map['n'] ?? ''}');
    if (n == null || n < 1 || n > 9999 || seen.contains(n)) continue;
    final text = '${map['text'] ?? ''}'.trim();
    if (text.length < 3) continue;
    seen.add(n);
    out.add(CiteRefEntry(
      n: n,
      text: text.length > 2000 ? text.substring(0, 2000) : text,
      doi: '${map['doi'] ?? ''}'.trim(),
    ));
  }
  out.sort((a, b) => a.n.compareTo(b.n));
  return out;
}
