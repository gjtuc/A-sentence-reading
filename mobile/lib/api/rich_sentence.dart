/// Allowed rich HTML → [InlineSpan] for sentence display (design/88 · 13).
///
/// Server stores only `<sub>` `<sup>` `<i>` `<em>` (no attributes).
/// EDGE: unknown tags stripped to text; malformed markup → plain fallback.
library;

import 'package:flutter/material.dart';

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

/// Strip all tags (for tests / plain fallback).
String plainFromRichHtml(String? raw) {
  final s = unescapeRichEntities((raw ?? '').trim());
  if (s.isEmpty) return '';
  if (!s.contains('<')) return s;
  return s.replaceAll(_tagRe, '').replaceAll(RegExp(r'\s+'), ' ').trim();
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
List<InlineSpan> buildRichSpans(String? raw, TextStyle base) {
  final src = unescapeRichEntities((raw ?? '').trim());
  if (src.isEmpty) return const [];
  if (!src.contains('<')) {
    return [TextSpan(text: src, style: base)];
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

InlineSpan _styledSpan(String text, TextStyle base, List<String> stack) {
  if (text.isEmpty) return const TextSpan(text: '');
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
}) {
  final plain = plainFromRichHtml(raw);
  if (plain.isEmpty) return buildRichSpans(raw, base);
  if (ranges.isEmpty) return buildRichSpans(raw, base);

  final merged = List<AnnotationRange>.from(ranges)
    ..sort((a, b) => a.start.compareTo(b.start));
  final out = <InlineSpan>[];
  var cursor = 0;
  for (final r in merged) {
    final start = r.start.clamp(0, plain.length);
    final end = r.end.clamp(start, plain.length);
    if (start > cursor) {
      out.addAll(buildRichSpans(plain.substring(cursor, start), base));
    }
    if (end > start) {
      final slice = plain.substring(start, end);
      final style = base.copyWith(
        backgroundColor: r.background.withValues(alpha: 0.4),
        decoration: r.underline ? TextDecoration.underline : null,
      );
      out.addAll(buildRichSpans(slice, style));
      cursor = end;
    }
  }
  if (cursor < plain.length) {
    out.addAll(buildRichSpans(plain.substring(cursor), base));
  }
  return out;
}
