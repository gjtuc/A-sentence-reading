/// Figure-panel ink palette + hit-test helpers (design/166).
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'annotation_models.dart';

/// 빨 · 파 · 초 · 보 · 흰 · 검정
const figureInkPalette = <String>[
  '#E53935',
  '#1E88E5',
  '#43A047',
  '#FDD835',
  '#FFFFFF',
  '#212121',
];

const String kDefaultFigureInkColor = '#E53935';

/// Half of the previous 2px pen. Saved strokes also paint at this width.
const double kFigureInkStrokeWidth = 1.0;

/// Strokes stay see-through so the figure underneath remains readable.
const double kFigureInkOpacity = 0.5;

enum FigureInkTool { pen, eraser }

/// Pen or eraser owns the finger. A cleared tool leaves pan and zoom on.
bool figureInkCapturesPointer({
  required bool inkMode,
  required FigureInkTool? tool,
}) {
  return inkMode && tool != null;
}

Color figureInkColorValue(String raw) {
  final s = raw.trim();
  if (s.startsWith('#') && s.length >= 7) {
    final hex = s.substring(1);
    final v = int.tryParse(hex.length >= 8 ? hex.substring(0, 6) : hex, radix: 16);
    if (v != null) {
      return Color(0xFF000000 | v);
    }
  }
  return const Color(0xFFE53935);
}

Color figureInkStrokeColor(String raw) {
  return figureInkColorValue(raw).withValues(alpha: kFigureInkOpacity);
}

/// Min distance from normalized point to an ink polyline (0–1 coords).
double inkPolylineDistanceNorm({
  required List<dynamic> points,
  required double nx,
  required double ny,
}) {
  if (points.length < 2) return double.infinity;
  var best = double.infinity;
  for (var i = 1; i < points.length; i++) {
    final a = points[i - 1];
    final b = points[i];
    if (a is! List || b is! List || a.length < 2 || b.length < 2) continue;
    final ax = (a[0] as num).toDouble();
    final ay = (a[1] as num).toDouble();
    final bx = (b[0] as num).toDouble();
    final by = (b[1] as num).toDouble();
    best = math.min(best, _pointSegmentDistanceNorm(nx, ny, ax, ay, bx, by));
  }
  return best;
}

double _pointSegmentDistanceNorm(
  double px,
  double py,
  double ax,
  double ay,
  double bx,
  double by,
) {
  final dx = bx - ax;
  final dy = by - ay;
  final len2 = dx * dx + dy * dy;
  if (len2 < 1e-12) {
    return math.sqrt((px - ax) * (px - ax) + (py - ay) * (py - ay));
  }
  var t = ((px - ax) * dx + (py - ay) * dy) / len2;
  t = t.clamp(0.0, 1.0);
  final cx = ax + t * dx;
  final cy = ay + t * dy;
  return math.sqrt((px - cx) * (px - cx) + (py - cy) * (py - cy));
}

/// Find first ink event id within [threshold] (normalized) of (nx, ny).
String? inkEventIdNearPoint({
  required List<AnnotationEvent> events,
  required double nx,
  required double ny,
  double threshold = 0.045,
}) {
  for (final ev in events) {
    if (!ev.isActive || ev.kind != 'ink') continue;
    for (final path in ev.paths) {
      final pts = path['points'];
      if (pts is! List) continue;
      final d = inkPolylineDistanceNorm(points: pts, nx: nx, ny: ny);
      if (d <= threshold) return ev.id;
    }
  }
  return null;
}
