/// Allowed rich HTML → [InlineSpan] for sentence display (design/88 · 13).
///
/// Server stores only `<sub>` `<sup>` `<i>` `<em>` (no attributes).
/// EDGE: unknown tags stripped to text; malformed markup → plain fallback.
library;

import 'package:flutter/material.dart';

import 'clause_breaks.dart';

const _allowed = {'sub', 'sup', 'i', 'em'};

final _tagRe = RegExp(r'</?([a-zA-Z0-9]+)(?:\s[^>]*)?>');
final _entitySub = RegExp(r'&lt;(/?)(sub|sup|i|em)&gt;', caseSensitive: false);

/// True when [raw] looks like it may contain rich markup (or escaped tags).
bool looksLikeRichHtml(String? raw) {
  if (raw == null || raw.isEmpty) return false;
  if (raw.contains('<')) return true;
  return _entitySub.hasMatch(raw);
}

/// Decode one layer of `&lt;sub&gt;` → `<sub>` so escaped markup can render.
String unescapeRichEntities(String raw) {
  if (!_entitySub.hasMatch(raw)) return raw;
  return raw.replaceAllMapped(_entitySub, (m) {
    final slash = m.group(1) ?? '';
    final tag = (m.group(2) ?? '').toLowerCase();
    return '<$slash$tag>';
  });
}

/// design/447 — the server escapes `<` `>` `&` in the text between tags
/// (`richtext.sanitize_sentence_html`). Decoded only after the tags are found, so
/// a printed `<` never opens a tag. Each entity is one character of plain text.
final _textEntity = RegExp(
  r'&(?:(amp|lt|gt|quot|apos)|#([0-9]{1,7})|#[xX]([0-9a-fA-F]{1,6}));',
);

const _namedEntity = {'amp': '&', 'lt': '<', 'gt': '>', 'quot': '"', 'apos': "'"};

String decodeTextEntities(String s) {
  if (!s.contains('&')) return s;
  return s.replaceAllMapped(_textEntity, (m) {
    final named = m.group(1);
    if (named != null) return _namedEntity[named]!;
    final code = int.tryParse(m.group(2) ?? m.group(3)!, radix: m.group(2) != null ? 10 : 16);
    if (code == null || code <= 0 || code > 0x10FFFF) return m.group(0)!;
    return String.fromCharCode(code);
  });
}

/// Strip all tags (for tests / plain fallback).
String plainFromRichHtml(String? raw) {
  final s = unescapeRichEntities((raw ?? '').trim());
  if (s.isEmpty) return '';
  if (!s.contains('<')) return decodeTextEntities(s);
  return decodeTextEntities(
    s.replaceAll(_tagRe, '').replaceAll(RegExp(r'\s+'), ' ').trim(),
  );
}

/// design/444 — [raw] with the clause breaks of its plain text as line breaks.
///
/// The breaks are chosen on [plainFromRichHtml], which drops tags and folds each
/// run of spaces into one, so the markup is walked the same way to find the
/// space each break stands for. A run that becomes a break loses its other spaces.
String richWithClauseBreaks(String? raw) {
  final src = unescapeRichEntities((raw ?? '').trim());
  if (src.isEmpty) return src;
  final breaks = clauseBreakOffsets(plainFromRichHtml(src));
  if (breaks.isEmpty) return src;
  if (!src.contains('&') && !src.contains('<')) {
    return withClauseBreaks(src, breaks);
  }
  // Without tags the plain text keeps every space; with tags it folds each run.
  final fold = src.contains('<');
  final tags = _tagRe.allMatches(src).toList();
  final out = StringBuffer();
  var p = 0;
  var t = 0;
  var i = 0;
  var started = false;
  var inSpace = false;
  var dropSpace = false;
  while (i < src.length) {
    if (t < tags.length && tags[t].start == i) {
      out.write(tags[t].group(0));
      i = tags[t].end;
      t++;
      continue;
    }
    final entity = src[i] == '&' ? _textEntity.matchAsPrefix(src, i) : null;
    if (entity != null) {
      out.write(entity.group(0));
      i = entity.end;
      started = true;
      inSpace = false;
      p++;
      continue;
    }
    final c = src[i];
    i++;
    if (c.trim().isEmpty) {
      if (!started) {
        out.write(c);
      } else if (!fold) {
        out.write(c == ' ' && breaks.contains(p) ? '\n' : c);
        p++;
      } else if (!inSpace) {
        inSpace = true;
        dropSpace = breaks.contains(p);
        out.write(dropSpace ? '\n' : c);
        p++;
      } else if (!dropSpace) {
        out.write(c);
      }
      continue;
    }
    started = true;
    inSpace = false;
    out.write(c);
    p++;
  }
  return out.toString();
}

/// Build a [Text.rich] for allowlisted sentence HTML.
Widget richSentenceText(
  String? raw, {
  required TextStyle style,
  TextAlign textAlign = TextAlign.start,
}) {
  final spans = buildRichSpans(raw, style);
  return Text.rich(
    TextSpan(style: style, children: spans),
    textAlign: textAlign,
  );
}

/// Parse into spans (unit-testable).
///
/// [trimInput] defaults true for full-sentence display. Annotated highlight
/// slices must pass false — otherwise leading/trailing spaces at range edges
/// are eaten and words glue together (design/182).
List<InlineSpan> buildRichSpans(
  String? raw,
  TextStyle base, {
  bool trimInput = true,
}) {
  final unescaped = unescapeRichEntities(raw ?? '');
  final src = trimInput ? unescaped.trim() : unescaped;
  if (src.isEmpty) return const [];
  if (!src.contains('<')) {
    return [TextSpan(text: decodeTextEntities(src), style: base)];
  }
  try {
    final out = <InlineSpan>[];
    _parse(src, 0, src.length, base, const [], out);
    if (out.isEmpty) {
      return [TextSpan(text: plainFromRichHtml(src), style: base)];
    }
    return out;
  } catch (_) {
    return [TextSpan(text: plainFromRichHtml(src), style: base)];
  }
}

void _parse(
  String src,
  int start,
  int end,
  TextStyle base,
  List<String> stack,
  List<InlineSpan> out,
) {
  var i = start;
  while (i < end) {
    final lt = src.indexOf('<', i);
    if (lt < 0 || lt >= end) {
      final text = src.substring(i, end);
      if (text.isNotEmpty) out.add(_styledSpan(text, base, stack));
      return;
    }
    if (lt > i) {
      out.add(_styledSpan(src.substring(i, lt), base, stack));
    }
    final gt = src.indexOf('>', lt + 1);
    if (gt < 0 || gt >= end) {
      out.add(_styledSpan(src.substring(lt, end), base, stack));
      return;
    }
    final token = src.substring(lt, gt + 1);
    final m = _tagRe.firstMatch(token);
    if (m == null) {
      out.add(_styledSpan(token, base, stack));
      i = gt + 1;
      continue;
    }
    final name = m.group(1)!.toLowerCase();
    final closing = token.startsWith('</');
    if (!_allowed.contains(name)) {
      // Drop unknown tags; keep inner text via continuing parse.
      i = gt + 1;
      continue;
    }
    if (closing) {
      i = gt + 1;
      return; // pop one level to caller
    }
    // Find matching close for this open tag (nested-aware).
    final closePat = RegExp('</$name>', caseSensitive: false);
    var depth = 1;
    var j = gt + 1;
    var closeAt = -1;
    while (j < end) {
      final nextOpen = RegExp('<$name(?:\\s[^>]*)?>', caseSensitive: false)
          .firstMatch(src.substring(j, end));
      final nextClose = closePat.firstMatch(src.substring(j, end));
      final openIdx = nextOpen == null ? -1 : j + nextOpen.start;
      final closeIdx = nextClose == null ? -1 : j + nextClose.start;
      if (closeIdx < 0) break;
      if (openIdx >= 0 && openIdx < closeIdx) {
        depth++;
        j = openIdx + nextOpen!.group(0)!.length;
        continue;
      }
      depth--;
      if (depth == 0) {
        closeAt = closeIdx;
        break;
      }
      j = closeIdx + nextClose!.group(0)!.length;
    }
    if (closeAt < 0) {
      // Unclosed: treat rest as text under this style.
      final nextStack = [...stack, name];
      _parse(src, gt + 1, end, base, nextStack, out);
      return;
    }
    final innerEnd = closeAt;
    final nextStack = [...stack, name];
    _parse(src, gt + 1, innerEnd, base, nextStack, out);
    i = closeAt + '</$name>'.length;
  }
}

InlineSpan _styledSpan(String raw, TextStyle base, List<String> stack) {
  if (raw.isEmpty) return const TextSpan(text: '');
  final text = decodeTextEntities(raw);
  var style = base;
  var isSub = false;
  var isSup = false;
  for (final t in stack) {
    if (t == 'i' || t == 'em') {
      style = style.copyWith(fontStyle: FontStyle.italic);
    } else if (t == 'sub') {
      isSub = true;
    } else if (t == 'sup') {
      isSup = true;
    }
  }
  if (!isSub && !isSup) {
    return TextSpan(text: text, style: style);
  }
  final size = (style.fontSize ?? 16) * 0.75;
  final dy = isSub ? 3.0 : -4.0;
  return WidgetSpan(
    alignment: PlaceholderAlignment.baseline,
    baseline: TextBaseline.alphabetic,
    child: Transform.translate(
      offset: Offset(0, dy),
      child: Text(text, style: style.copyWith(fontSize: size)),
    ),
  );
}

/// Highlight range on plain-text offsets (design/166).
class AnnotationRange {
  const AnnotationRange({
    required this.start,
    required this.end,
    required this.background,
    this.underline = false,
  });

  final int start;
  final int end;
  final Color background;
  final bool underline;
}

List<InlineSpan> buildAnnotatedSpans(
  String? raw,
  TextStyle base, {
  List<AnnotationRange> ranges = const [],
  /// When true, always index by [plainFromRichHtml] even if [ranges] is empty.
  /// Needed for paint mode: switching rich→plain when the first preview range
  /// appears changes layout mid-gesture and cancels the pan (design/182).
  bool plainMetrics = false,
  /// design/444 — show the sentence in its pieces. Offsets do not move.
  bool clauseBreaks = false,
}) {
  final plain = plainFromRichHtml(raw);
  if (plain.isEmpty) return buildRichSpans(raw, base);
  if (ranges.isEmpty && !plainMetrics) {
    return buildRichSpans(clauseBreaks ? richWithClauseBreaks(raw) : raw, base);
  }
  final shown =
      clauseBreaks ? withClauseBreaks(plain, clauseBreakOffsets(plain)) : plain;

  // Later ranges win on overlap (caller should pass in ascending `at` order).
  final cover = List<AnnotationRange?>.filled(plain.length, null);
  for (final r in ranges) {
    final start = r.start.clamp(0, plain.length);
    final end = r.end.clamp(start, plain.length);
    for (var i = start; i < end; i++) {
      cover[i] = r;
    }
  }

  final out = <InlineSpan>[];
  var i = 0;
  while (i < plain.length) {
    final active = cover[i];
    var j = i + 1;
    while (j < plain.length && _sameAnnotStyle(cover[j], active)) {
      j++;
    }
    // Already plain and decoded: a printed `<` or `&gt;` must stay as it reads.
    final slice = shown.substring(i, j);
    if (active == null) {
      out.add(TextSpan(text: slice, style: base));
    } else {
      final style = base.copyWith(
        backgroundColor: active.background.withValues(alpha: 0.4),
        decoration: active.underline ? TextDecoration.underline : null,
      );
      out.add(TextSpan(text: slice, style: style));
    }
    i = j;
  }
  return out;
}

bool _sameAnnotStyle(AnnotationRange? a, AnnotationRange? b) {
  if (a == null && b == null) return true;
  if (a == null || b == null) return false;
  return a.background == b.background && a.underline == b.underline;
}
