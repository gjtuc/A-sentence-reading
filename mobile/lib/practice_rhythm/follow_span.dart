/// Follow-light span on the printed chunk (design/313).
library;

import 'package:flutter/painting.dart';

class FollowSpan {
  const FollowSpan({
    required this.start,
    required this.end,
    required this.weight,
  });

  final int start;
  final int end;
  final int weight;
}

/// Media-time position picks the printed span. Weight 0 spans are skipped.
FollowSpan? activeFollowSpan(
  List<FollowSpan> spans,
  int positionMs,
  int durationMs,
) {
  if (durationMs <= 0 || spans.isEmpty) return null;
  var total = 0;
  for (final s in spans) {
    if (s.weight > 0) total += s.weight;
  }
  if (total <= 0) return null;
  final target = positionMs / durationMs * total;
  var acc = 0.0;
  FollowSpan? last;
  for (final s in spans) {
    if (s.weight <= 0) continue;
    last = s;
    acc += s.weight;
    if (target < acc) return s;
  }
  return last;
}

/// Scroll offset that brings [start, end) into view. Null if already visible.
///
/// Uses layout only. The caller must pass the player media clock, not a
/// rate-adjusted wall clock (design/313).
double? followRevealOffset({
  required String text,
  required TextStyle style,
  required int start,
  required int end,
  required double maxWidth,
  required double viewportHeight,
  required double currentOffset,
}) {
  if (maxWidth <= 0 || viewportHeight <= 0) return null;
  if (start < 0 || end <= start || end > text.length) return null;
  final painter = TextPainter(
    text: TextSpan(text: text, style: style),
    textDirection: TextDirection.ltr,
    textAlign: TextAlign.center,
  )..layout(maxWidth: maxWidth);
  final boxes = painter.getBoxesForSelection(
    TextSelection(baseOffset: start, extentOffset: end),
  );
  if (boxes.isEmpty) return null;
  final top = boxes.first.top;
  final bottom = boxes.last.bottom;
  const pad = 8.0;
  if (top >= currentOffset + pad &&
      bottom <= currentOffset + viewportHeight - pad) {
    return null;
  }
  final maxExtent =
      painter.height > viewportHeight ? painter.height - viewportHeight : 0.0;
  var target = top - pad;
  if (target < 0) target = 0;
  if (target > maxExtent) target = maxExtent;
  if ((target - currentOffset).abs() < 1) return null;
  return target;
}
