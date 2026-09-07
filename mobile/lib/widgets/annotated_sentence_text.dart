import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import '../api/annotation_models.dart';
import '../api/annotation_plain.dart';
import '../api/rich_sentence.dart';

/// Sentence body with highlight overlays + latched word paint (design/166 · 182).
class AnnotatedSentenceText extends StatefulWidget {
  const AnnotatedSentenceText({
    super.key,
    required this.html,
    required this.style,
    this.annotations = const [],
    this.textAlign = TextAlign.start,
    this.paintMode = false,
    this.paintColor,
    this.previewStart,
    this.previewEnd,
    this.onPaintPreview,
    this.onPaintCommitted,
    this.onPaintCancel,
  });

  final String html;
  final TextStyle style;
  final List<AnnotationEvent> annotations;
  final TextAlign textAlign;

  /// Latched highlighter: pointer-down selects a word; drag expands by words.
  final bool paintMode;
  final String? paintColor;
  final int? previewStart;
  final int? previewEnd;
  final void Function(int start, int end)? onPaintPreview;
  final void Function(int start, int end)? onPaintCommitted;
  final VoidCallback? onPaintCancel;

  @override
  State<AnnotatedSentenceText> createState() => _AnnotatedSentenceTextState();
}

class _AnnotatedSentenceTextState extends State<AnnotatedSentenceText> {
  final GlobalKey _textKey = GlobalKey();
  int? _activePointer;
  int? _anchorWordStart;
  int? _anchorWordEnd;

  String get _plain => annotationPlainForSentence(widget.html);

  List<AnnotationRange> _persistedRanges() {
    final plainLen = _plain.length;
    final ranges = <AnnotationRange>[];
    final events = List<AnnotationEvent>.from(widget.annotations)
      ..sort((a, b) => a.at.compareTo(b.at));
    for (final ev in events) {
      if (!ev.isActive || ev.kind == 'ink') continue;
      final bg = annotationColorValue(ev.color);
      final cr = ev.charRange;
      if (cr != null && cr.length == 2) {
        ranges.add(AnnotationRange(
          start: cr[0],
          end: cr[1],
          background: bg,
          underline: ev.kind == 'underline',
        ));
      } else {
        ranges.add(AnnotationRange(
          start: 0,
          end: plainLen,
          background: bg,
          underline: ev.kind == 'underline',
        ));
      }
    }
    return ranges;
  }

  List<AnnotationRange> _rangesForPaint() {
    final ranges = _persistedRanges();
    final ps = widget.previewStart;
    final pe = widget.previewEnd;
    final pc = widget.paintColor;
    if (widget.paintMode && ps != null && pe != null && pc != null) {
      final clamped = clampCharRange(ps, pe, _plain.length);
      if (clamped != null) {
        ranges.add(AnnotationRange(
          start: clamped[0],
          end: clamped[1],
          background: annotationColorValue(pc),
        ));
      }
    }
    return ranges;
  }

  /// Hit-test without paint preview (stable layout while dragging).
  int? _indexForGlobal(Offset global) {
    final ctx = _textKey.currentContext;
    if (ctx == null) return null;
    final box = ctx.findRenderObject();
    if (box is! RenderBox || !box.hasSize) return null;
    final local = box.globalToLocal(global);
    final spans = buildAnnotatedSpans(
      widget.html,
      widget.style,
      ranges: _persistedRanges(),
    );
    final tp = TextPainter(
      text: TextSpan(style: widget.style, children: spans),
      textAlign: widget.textAlign,
      textDirection: TextDirection.ltr,
    )..layout(maxWidth: box.size.width);
    final pos = tp.getPositionForOffset(local);
    return pos.offset.clamp(0, _plain.length);
  }

  void _clearDrag() {
    _activePointer = null;
    _anchorWordStart = null;
    _anchorWordEnd = null;
  }

  void _onPointerDown(PointerDownEvent e) {
    if (!widget.paintMode) return;
    if (e.buttons != kPrimaryButton) return;
    final idx = _indexForGlobal(e.position);
    if (idx == null) return;
    final word = wordRangeAt(_plain, idx);
    if (word == null) {
      widget.onPaintCancel?.call();
      return;
    }
    _activePointer = e.pointer;
    _anchorWordStart = word[0];
    _anchorWordEnd = word[1];
    widget.onPaintPreview?.call(word[0], word[1]);
  }

  void _onPointerMove(PointerMoveEvent e) {
    if (!widget.paintMode || e.pointer != _activePointer) return;
    final a0 = _anchorWordStart;
    final a1 = _anchorWordEnd;
    if (a0 == null || a1 == null) return;
    final idx = _indexForGlobal(e.position);
    if (idx == null) return;
    final snapped = wordSnappedSelection(
      plain: _plain,
      anchorStart: a0,
      anchorEnd: a1,
      extentIndex: idx,
    );
    if (snapped == null) return;
    widget.onPaintPreview?.call(snapped[0], snapped[1]);
  }

  void _onPointerUp(PointerUpEvent e) {
    if (!widget.paintMode || e.pointer != _activePointer) return;
    final start = widget.previewStart ?? _anchorWordStart;
    final end = widget.previewEnd ?? _anchorWordEnd;
    _clearDrag();
    if (start == null || end == null) {
      widget.onPaintCancel?.call();
      return;
    }
    final clamped = clampCharRange(start, end, _plain.length);
    if (clamped == null) {
      widget.onPaintCancel?.call();
      return;
    }
    widget.onPaintCommitted?.call(clamped[0], clamped[1]);
  }

  void _onPointerCancel(PointerCancelEvent e) {
    if (e.pointer != _activePointer) return;
    _clearDrag();
    widget.onPaintCancel?.call();
  }

  @override
  Widget build(BuildContext context) {
    final spans = buildAnnotatedSpans(
      widget.html,
      widget.style,
      ranges: _rangesForPaint(),
    );
    final text = Text.rich(
      TextSpan(style: widget.style, children: spans),
      key: _textKey,
      textAlign: widget.textAlign,
    );
    if (!widget.paintMode) return text;
    return Listener(
      behavior: HitTestBehavior.translucent,
      onPointerDown: _onPointerDown,
      onPointerMove: _onPointerMove,
      onPointerUp: _onPointerUp,
      onPointerCancel: _onPointerCancel,
      child: text,
    );
  }
}
