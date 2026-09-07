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

final _wordCharRe = RegExp(
  r"[0-9A-Za-z\u00C0-\u024F\u0400-\u04FF\u0900-\u097F\u4E00-\u9FFF"
  r"\uAC00-\uD7A3\u3040-\u30FF'’\-]",
);

bool isAnnotationWordChar(String plain, int index) {
  if (index < 0 || index >= plain.length) return false;
  return _wordCharRe.hasMatch(plain[index]);
}

/// Word (or contiguous word-chars) enclosing [index], half-open [start, end).
/// If [index] is on whitespace/punct, snaps to the nearest word (prefer left).
List<int>? wordRangeAt(String plain, int index) {
  if (plain.isEmpty) return null;
  var i = index.clamp(0, plain.length);
  if (i == plain.length) i = plain.length - 1;
  if (!isAnnotationWordChar(plain, i)) {
    var found = -1;
    for (var L = i; L >= 0; L--) {
      if (isAnnotationWordChar(plain, L)) {
        found = L;
        break;
      }
    }
    if (found < 0) {
      for (var R = i; R < plain.length; R++) {
        if (isAnnotationWordChar(plain, R)) {
          found = R;
          break;
        }
      }
    }
    if (found < 0) return null;
    i = found;
  }
  var start = i;
  while (start > 0 && isAnnotationWordChar(plain, start - 1)) {
    start--;
  }
  var end = i + 1;
  while (end < plain.length && isAnnotationWordChar(plain, end)) {
    end++;
  }
  return [start, end];
}

/// Expand anchor word range and the word at [extentIndex] (latched highlighter).
List<int>? wordSnappedSelection({
  required String plain,
  required int anchorStart,
  required int anchorEnd,
  required int extentIndex,
}) {
  final a = clampCharRange(anchorStart, anchorEnd, plain.length);
  final extent = wordRangeAt(plain, extentIndex);
  if (a == null && extent == null) return null;
  final starts = <int>[
    if (a != null) a[0],
    if (extent != null) extent[0],
  ];
  final ends = <int>[
    if (a != null) a[1],
    if (extent != null) extent[1],
  ];
  final start = starts.reduce((x, y) => x < y ? x : y);
  final end = ends.reduce((x, y) => x > y ? x : y);
  return clampCharRange(start, end, plain.length);
}
