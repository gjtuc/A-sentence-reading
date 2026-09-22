/// Union bbox helpers for figure layout edit (design/163).
library;

import 'package:flutter/material.dart';

import '../widgets/layout_overlay.dart';

class NormRect {
  const NormRect({
    required this.left,
    required this.top,
    required this.right,
    required this.bottom,
  });

  final double left;
  final double top;
  final double right;
  final double bottom;

  bool get isValid => right > left && bottom > top;
}

NormRect unionBoxes(List<LayoutBoxView> boxes) {
  if (boxes.isEmpty) {
    return const NormRect(left: 0, top: 0, right: 0, bottom: 0);
  }
  var l = boxes.first.left;
  var t = boxes.first.top;
  var r = boxes.first.right;
  var b = boxes.first.bottom;
  for (final box in boxes.skip(1)) {
    l = l < box.left ? l : box.left;
    t = t < box.top ? t : box.top;
    r = r > box.right ? r : box.right;
    b = b > box.bottom ? b : box.bottom;
  }
  return NormRect(left: l, top: t, right: r, bottom: b);
}

bool samePage(List<LayoutBoxView> boxes) {
  if (boxes.isEmpty) return true;
  final page = boxes.first.pageIndex;
  return boxes.every((b) => b.pageIndex == page);
}

NormRect normRectFromDrag({
  required Offset start,
  required Offset end,
  required Size size,
}) {
  final width = size.width <= 0 ? 1.0 : size.width;
  final height = size.height <= 0 ? 1.0 : size.height;
  final x0 = (start.dx < end.dx ? start.dx : end.dx) / width;
  final x1 = (start.dx > end.dx ? start.dx : end.dx) / width;
  final y0 = (start.dy < end.dy ? start.dy : end.dy) / height;
  final y1 = (start.dy > end.dy ? start.dy : end.dy) / height;
  return NormRect(
    left: x0.clamp(0.0, 1.0),
    top: y0.clamp(0.0, 1.0),
    right: x1.clamp(0.0, 1.0),
    bottom: y1.clamp(0.0, 1.0),
  );
}

/// Page image rect inside a view when the page is [BoxFit.contain] centered.
Rect fittedContainRect(Size view, double aspectRatio) {
  if (!view.width.isFinite ||
      !view.height.isFinite ||
      view.width <= 0 ||
      view.height <= 0 ||
      !aspectRatio.isFinite ||
      aspectRatio <= 0) {
    return Rect.zero;
  }
  final viewAspect = view.width / view.height;
  if (viewAspect > aspectRatio) {
    final w = view.height * aspectRatio;
    return Rect.fromLTWH((view.width - w) / 2, 0, w, view.height);
  }
  final h = view.width / aspectRatio;
  return Rect.fromLTWH(0, (view.height - h) / 2, view.width, h);
}

/// A crop drag is kept when it is a real rectangle, not a tap.
bool cropDragKept(NormRect rect, Size pageSize, {double minPx = 8}) {
  if (!rect.isValid || pageSize.width <= 0 || pageSize.height <= 0) {
    return false;
  }
  final w = (rect.right - rect.left) * pageSize.width;
  final h = (rect.bottom - rect.top) * pageSize.height;
  return w >= minPx && h >= minPx;
}

enum PanEdgeTurn { none, previous, next }

/// Which content edges are already on screen before this gesture.
({bool left, bool right}) viewerContentEdges({
  required double sceneLeft,
  required double sceneRight,
  required double childWidth,
  required double scale,
}) {
  if (childWidth <= 0 || !scale.isFinite || scale <= 0) {
    return (left: false, right: false);
  }
  final slop = 8.0 / scale;
  return (
    left: sceneLeft <= slop,
    right: sceneRight >= childWidth - slop,
  );
}

/// Page turn only when the gesture started on that edge and pulls past it.
///
/// A pan that begins in the middle stays a pan, even if it ends on an edge.
PanEdgeTurn panEdgePageTurn({
  required bool atLeftEdge,
  required bool atRightEdge,
  required double dx,
  required double dy,
  required double vx,
  required double vy,
  required int pointerCount,
  required bool pulledPastLeft,
  required bool pulledPastRight,
  double minDistance = 36,
  double minVelocity = 450,
}) {
  if (pointerCount >= 2) return PanEdgeTurn.none;
  if (vx.abs() < vy.abs() && dx.abs() < dy.abs()) return PanEdgeTurn.none;
  final next = atRightEdge &&
      (pulledPastRight || dx <= -minDistance || vx <= -minVelocity);
  final prev = atLeftEdge &&
      (pulledPastLeft || dx >= minDistance || vx >= minVelocity);
  if (next && prev) {
    if (vx < 0 || (vx.abs() < 1 && dx < 0)) return PanEdgeTurn.next;
    if (vx > 0 || (vx.abs() < 1 && dx > 0)) return PanEdgeTurn.previous;
    return PanEdgeTurn.none;
  }
  if (next) return PanEdgeTurn.next;
  if (prev) return PanEdgeTurn.previous;
  return PanEdgeTurn.none;
}

LayoutBoxView manualBox({
  required String id,
  required int pageIndex,
  required NormRect rect,
  String kind = 'figure_body',
}) {
  return LayoutBoxView(
    id: id,
    pageIndex: pageIndex,
    kind: kind,
    left: rect.left,
    top: rect.top,
    right: rect.right,
    bottom: rect.bottom,
  );
}
