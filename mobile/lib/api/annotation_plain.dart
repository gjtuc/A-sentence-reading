/// Plain offset + TextQuoteSelector helpers (design/182).
///
/// Display, paint, clipboard, and selectors MUST use [annotationPlainForSentence]
/// so cite-strip + rich-plain stay aligned.
library;

import 'cite_refs.dart';
import 'rich_sentence.dart';

/// Exact display/paint plain for a sentence body (182 §8.1).
String annotationPlainForSentence(String? rawHtml) {
  return plainFromRichHtml(stripCiteMarkersForDisplay(rawHtml));
}

/// Clamp half-open [start, end) into [0, length]. Returns null if empty.
List<int>? clampCharRange(int start, int end, int length) {
  if (length <= 0) return null;
  var s = start;
  var e = end;
  if (e < s) {
    final t = s;
    s = e;
    e = t;
  }
  s = s.clamp(0, length);
  e = e.clamp(s, length);
  if (e <= s) return null;
  return [s, e];
}

/// W3C-style TextQuoteSelector for a plain substring (reanchor / 182).
Map<String, dynamic> textQuoteSelectorForRange(
  String plain,
  int start,
  int end, {
  int contextChars = 12,
}) {
  final clamped = clampCharRange(start, end, plain.length);
  final s = clamped?[0] ?? 0;
  final e = clamped?[1] ?? 0;
  final exact = (clamped == null) ? '' : plain.substring(s, e);
  final prefixStart = (s - contextChars).clamp(0, plain.length);
  final suffixEnd = (e + contextChars).clamp(0, plain.length);
  final prefix = s > prefixStart ? plain.substring(prefixStart, s) : '';
  final suffix = suffixEnd > e ? plain.substring(e, suffixEnd) : '';
  return {
    'type': 'TextQuoteSelector',
    'exact': exact,
    if (prefix.isNotEmpty) 'prefix': prefix,
    if (suffix.isNotEmpty) 'suffix': suffix,
  };
}

/// Recompute [start, end) from selector exact within [plain], or null.
List<int>? charRangeFromSelectorExact(String plain, Map<String, dynamic>? selector) {
  if (selector == null || plain.isEmpty) return null;
  final exact = plainFromRichHtml('${selector['exact'] ?? ''}');
  if (exact.isEmpty) return null;
  final idx = plain.toLowerCase().indexOf(exact.toLowerCase());
  if (idx < 0) return null;
  return clampCharRange(idx, idx + exact.length, plain.length);
}
