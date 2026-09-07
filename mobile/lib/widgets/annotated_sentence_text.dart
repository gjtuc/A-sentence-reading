import 'package:flutter/material.dart';

import '../api/annotation_models.dart';
import '../api/annotation_plain.dart';
import '../api/rich_sentence.dart';

/// Sentence body with highlight overlays + optional paint drag (design/166 · 182).
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

  /// When true, pan selects a plain char range inside this sentence only.
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
  int? _dragAnchor;

  String get _plain => annotationPlainForSentence(widget.html);

  List<AnnotationRange> _ranges() {
    final plainLen = _plain.length;
    final ranges = <AnnotationRange>[];
    // Stable order: older first so later events win in buildAnnotatedSpans.
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
    final ps = widget.previewStart;
    final pe = widget.previewEnd;
    final pc = widget.paintColor;
    if (widget.paintMode && ps != null && pe != null && pc != null) {
      final clamped = clampCharRange(ps, pe, plainLen);
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

  int? _indexForGlobal(Offset global) {
    final ctx = _textKey.currentContext;
    if (ctx == null) return null;
    final box = ctx.findRenderObject();
    if (box is! RenderBox || !box.hasSize) return null;
    final local = box.globalToLocal(global);
    final spans = buildAnnotatedSpans(widget.html, widget.style, ranges: _ranges());
    final tp = TextPainter(
      text: TextSpan(style: widget.style, children: spans),
      textAlign: widget.textAlign,
      textDirection: TextDirection.ltr,
    )..layout(maxWidth: box.size.width);
    final pos = tp.getPositionForOffset(local);
    return pos.offset.clamp(0, _plain.length);
  }

  void _onPanStart(DragStartDetails d) {
    if (!widget.paintMode) return;
    final idx = _indexForGlobal(d.globalPosition);
    if (idx == null) return;
    _dragAnchor = idx;
    widget.onPaintPreview?.call(idx, idx);
  }

  void _onPanUpdate(DragUpdateDetails d) {
    if (!widget.paintMode || _dragAnchor == null) return;
    // Prefer horizontal paint; large vertical movement cancels into scroll.
    if (d.delta.dy.abs() > 12 && d.delta.dy.abs() > d.delta.dx.abs() * 1.5) {
      return;
    }
    final idx = _indexForGlobal(d.globalPosition);
    if (idx == null) return;
    widget.onPaintPreview?.call(_dragAnchor!, idx);
  }

  void _onPanEnd(DragEndDetails d) {
    if (!widget.paintMode || _dragAnchor == null) return;
    final start = widget.previewStart ?? _dragAnchor!;
    final end = widget.previewEnd ?? _dragAnchor!;
    _dragAnchor = null;
    final clamped = clampCharRange(start, end, _plain.length);
    if (clamped == null) {
      widget.onPaintCancel?.call();
      return;
    }
    widget.onPaintCommitted?.call(clamped[0], clamped[1]);
  }

  void _onPanCancel() {
    _dragAnchor = null;
    widget.onPaintCancel?.call();
  }

  @override
  Widget build(BuildContext context) {
    final spans = buildAnnotatedSpans(widget.html, widget.style, ranges: _ranges());
    final text = Text.rich(
      TextSpan(style: widget.style, children: spans),
      key: _textKey,
      textAlign: widget.textAlign,
    );
    if (!widget.paintMode) return text;
    return GestureDetector(
      behavior: HitTestBehavior.translucent,
      onPanStart: _onPanStart,
      onPanUpdate: _onPanUpdate,
      onPanEnd: _onPanEnd,
      onPanCancel: _onPanCancel,
      onTap: widget.onPaintCancel,
      child: text,
    );
  }
}
