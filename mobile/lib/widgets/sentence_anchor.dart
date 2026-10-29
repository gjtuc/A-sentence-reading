/// design/480 — every sentence starts at one place, and a faint mark shows it.
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';

/// The first line of a sentence starts this share of the window's height below
/// the top of its pane. It is pixels, not a share of the pane: the pane grows
/// and shrinks as a figure opens beside the sentence, and the start stays put.
const double kSentenceStartAt = 0.2;

/// design/484 — on the phone the first line starts this far below the top of its
/// pane, in every layout: room for a section name of [fontSize] text above it and
/// no more. A narrow phone wraps a sentence into many lines, and a section name
/// that did not fit would push its sentence below where the others start.
double phoneSentenceStart(double fontSize) =>
    math.max(12.0, fontSize * 0.55) * 1.5 + fontSize * 0.9;

/// Where the sentence's first line goes in a pane [view] tall: [start] down,
/// raised only as far as a long sentence needs to fit, and never over the
/// [head] above it.
double sentenceTop({
  required double view,
  required double head,
  required double body,
  required double start,
}) =>
    math.max(head, math.min(start, view - body));

/// [body] (the sentence and what follows it) starts at [sentenceTop]; [head]
/// (the sentence before it, a section name) sits right above, so its height
/// does not push the sentence. Short and long sentences start at one height
/// and the eye finds the next one where the last one began.
class SentenceAnchor extends MultiChildRenderObjectWidget {
  SentenceAnchor({
    super.key,
    required Widget head,
    required Widget body,
    required this.viewHeight,
    this.startPx,
  }) : super(children: [head, body]);

  final double viewHeight;

  /// The start in pixels below the pane's top, in place of [kSentenceStartAt].
  final double? startPx;

  /// [startPx], else [kSentenceStartAt] of the window, or of [viewHeight] without one.
  double _start(BuildContext context) {
    if (startPx case final double px) return px;
    final window = MediaQuery.maybeSizeOf(context)?.height;
    final h = window != null && window > 0 ? window : viewHeight;
    return h.isFinite ? h * kSentenceStartAt : 0;
  }

  @override
  RenderSentenceAnchor createRenderObject(BuildContext context) =>
      RenderSentenceAnchor(viewHeight: viewHeight, start: _start(context));

  @override
  void updateRenderObject(BuildContext context, RenderSentenceAnchor renderObject) {
    renderObject
      ..viewHeight = viewHeight
      ..start = _start(context);
  }
}

class _AnchorParentData extends ContainerBoxParentData<RenderBox> {}

class RenderSentenceAnchor extends RenderBox
    with
        ContainerRenderObjectMixin<RenderBox, _AnchorParentData>,
        RenderBoxContainerDefaultsMixin<RenderBox, _AnchorParentData> {
  RenderSentenceAnchor({required double viewHeight, required double start})
      : _viewHeight = viewHeight,
        _start = start;

  double _viewHeight;
  set viewHeight(double value) {
    if (value == _viewHeight) return;
    _viewHeight = value;
    markNeedsLayout();
  }

  double _start;
  set start(double value) {
    if (value == _start) return;
    _start = value;
    markNeedsLayout();
  }

  double get _view => _viewHeight.isFinite ? math.max(0.0, _viewHeight) : 0.0;

  @override
  void setupParentData(RenderBox child) {
    if (child.parentData is! _AnchorParentData) child.parentData = _AnchorParentData();
  }

  BoxConstraints _childConstraints(BoxConstraints c) =>
      BoxConstraints(minWidth: c.minWidth, maxWidth: c.maxWidth);

  Size _place(BoxConstraints c, Size head, Size body, {List<double>? tops}) {
    final top = sentenceTop(view: _view, head: head.height, body: body.height, start: _start);
    tops?.addAll([top - head.height, top]);
    final width = c.hasBoundedWidth ? c.maxWidth : math.max(head.width, body.width);
    return c.constrain(Size(width, math.max(_view, top + body.height)));
  }

  @override
  void performLayout() {
    final head = firstChild!;
    final body = childAfter(head)!;
    final cc = _childConstraints(constraints);
    head.layout(cc, parentUsesSize: true);
    body.layout(cc, parentUsesSize: true);
    final tops = <double>[];
    size = _place(constraints, head.size, body.size, tops: tops);
    (head.parentData! as _AnchorParentData).offset = Offset(0, tops[0]);
    (body.parentData! as _AnchorParentData).offset = Offset(0, tops[1]);
  }

  @override
  Size computeDryLayout(covariant BoxConstraints constraints) {
    final head = firstChild!;
    final body = childAfter(head)!;
    final cc = _childConstraints(constraints);
    return _place(constraints, head.getDryLayout(cc), body.getDryLayout(cc));
  }

  double _widest(double Function(RenderBox) f) {
    var w = 0.0;
    for (var c = firstChild; c != null; c = childAfter(c)) {
      w = math.max(w, f(c));
    }
    return w;
  }

  @override
  double computeMinIntrinsicWidth(double height) => _widest((c) => c.getMinIntrinsicWidth(height));

  @override
  double computeMaxIntrinsicWidth(double height) => _widest((c) => c.getMaxIntrinsicWidth(height));

  double _tall(double width, double Function(RenderBox) f) {
    final head = firstChild!;
    final body = childAfter(head)!;
    final top = sentenceTop(view: _view, head: f(head), body: f(body), start: _start);
    return math.max(_view, top + f(body));
  }

  @override
  double computeMinIntrinsicHeight(double width) => _tall(width, (c) => c.getMinIntrinsicHeight(width));

  @override
  double computeMaxIntrinsicHeight(double width) => _tall(width, (c) => c.getMaxIntrinsicHeight(width));

  @override
  void paint(PaintingContext context, Offset offset) => defaultPaint(context, offset);

  @override
  bool hitTestChildren(BoxHitTestResult result, {required Offset position}) =>
      defaultHitTestChildren(result, position: position);
}

/// A faint bar left of a sentence's first line. It does not move: when the
/// sentence arrives it brightens for a moment, so the eye jumps once to where the
/// sentence starts instead of looking for it, then fades away (design/482).
class StartMark extends StatefulWidget {
  const StartMark({super.key, required this.height});

  final double height;

  static const double width = 3;
  static const Duration life = Duration(milliseconds: 3000);

  /// Opacity as the sentence arrives, and at the top of its brightening.
  static const double rest = 0.16;
  static const double peak = 0.3;

  /// The bar's opacity [s] seconds after the turn: it waits while the old sentence
  /// dims, brightens as the new one comes, then fades without a pause until it is
  /// gone at [life]. A hold before fading would show the moment the fade begins.
  static double alphaAt(double s) {
    final end = life.inMilliseconds / 1000;
    if (s <= 0.105) return rest;
    if (s < 0.21) return rest + (peak - rest) * Curves.easeOut.transform((s - 0.105) / 0.105);
    if (s < 0.7) return peak - (peak - rest) * Curves.easeOut.transform((s - 0.21) / 0.49);
    if (s >= end) return 0;
    return rest * (1 - Curves.easeInOut.transform((s - 0.7) / (end - 0.7)));
  }

  @override
  State<StartMark> createState() => _StartMarkState();
}

class _StartMarkState extends State<StartMark> with SingleTickerProviderStateMixin {
  late final AnimationController _pulse = AnimationController(
    vsync: this,
    duration: StartMark.life,
    animationBehavior: AnimationBehavior.preserve,
  )..forward();

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final ink = Theme.of(context).colorScheme.onSurface;
    return ExcludeSemantics(
      child: IgnorePointer(
        child: AnimatedBuilder(
          animation: _pulse,
          builder: (context, _) => Container(
            width: StartMark.width,
            height: widget.height,
            decoration: BoxDecoration(
              color: ink.withValues(
                  alpha: StartMark.alphaAt(
                      _pulse.value * StartMark.life.inMilliseconds / 1000)),
              borderRadius: BorderRadius.circular(StartMark.width / 2),
            ),
          ),
        ),
      ),
    );
  }
}

/// [sentence] with a [StartMark] in the [gutter] to its left, as tall as its
/// letters and level with its first line. A gutter too thin for it gets none;
/// the phone passes 0, since a hand-swiped sentence needs no finding (design/483).
Widget withStartMark(Widget sentence, {required TextStyle style, required double gutter}) {
  if (gutter < 6) return sentence;
  final px = style.fontSize ?? 18;
  final line = px * (style.height ?? 1.3);
  final mid = math.min(gutter / 2, 8.0);
  return Stack(
    clipBehavior: Clip.none,
    children: [
      sentence,
      Positioned(
        left: -mid - StartMark.width / 2,
        top: (line - px) / 2,
        child: StartMark(height: px),
      ),
    ],
  );
}
