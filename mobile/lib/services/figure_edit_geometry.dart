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
  final x0 = (start.dx < end.dx ? start.dx : end.dx) / size.width;
  final x1 = (start.dx > end.dx ? start.dx : end.dx) / size.width;
  final y0 = (start.dy < end.dy ? start.dy : end.dy) / size.height;
  final y1 = (start.dy > end.dy ? start.dy : end.dy) / size.height;
  return NormRect(
    left: x0.clamp(0.0, 1.0),
    top: y0.clamp(0.0, 1.0),
    right: x1.clamp(0.0, 1.0),
    bottom: y1.clamp(0.0, 1.0),
  );
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
