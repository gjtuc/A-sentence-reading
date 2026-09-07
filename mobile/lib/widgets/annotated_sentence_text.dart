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

  /// Latched highlighter: touch selects a word; drag expands by words.
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
  int? _anchorWordStart;
  int? _anchorWordEnd;
  bool _dragging = false;

  /// Local preview so paint drag does not rebuild the whole reader.
  int? _localPreviewStart;
  int? _localPreviewEnd;

  String get _plain => annotationPlainForSentence(widget.html);

  int? get _previewStart => _localPreviewStart ?? widget.previewStart;
  int? get _previewEnd => _localPreviewEnd ?? widget.previewEnd;

  @override
  void didUpdateWidget(covariant AnnotatedSentenceText oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!widget.paintMode && oldWidget.paintMode) {
      _dragging = false;
      _anchorWordStart = null;
      _anchorWordEnd = null;
      _localPreviewStart = null;
      _localPreviewEnd = null;
    }
  }

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
    final ps = _previewStart;
    final pe = _previewEnd;
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

  /// Same span path as display (plainMetrics while painting). Preview omitted
  /// so glyph positions stay fixed while the highlight grows.
  int? _indexForGlobal(Offset global) {
    final ctx = _textKey.currentContext;
    if (ctx == null) return null;
    final box = ctx.findRenderObject();
    if (box is! RenderBox || !box.hasSize) return null;
    final local = box.globalToLocal(global);
    final clampedLocal = Offset(
      local.dx.clamp(0.0, box.size.width),
      local.dy.clamp(0.0, box.size.height),
    );
    final spans = buildAnnotatedSpans(
      widget.html,
      widget.style,
      ranges: _persistedRanges(),
      plainMetrics: widget.paintMode,
    );
    final tp = TextPainter(
      text: TextSpan(style: widget.style, children: spans),
      textAlign: widget.textAlign,
      textDirection: TextDirection.ltr,
    )..layout(maxWidth: box.size.width);
    final pos = tp.getPositionForOffset(clampedLocal);
    return pos.offset.clamp(0, _plain.length);
  }

  void _setLocalPreview(int start, int end) {
    if (_localPreviewStart == start && _localPreviewEnd == end) return;
    setState(() {
      _localPreviewStart = start;
      _localPreviewEnd = end;
    });
    widget.onPaintPreview?.call(start, end);
  }

  void _onPanStart(DragStartDetails d) {
    if (!widget.paintMode) return;
    final idx = _indexForGlobal(d.globalPosition);
    if (idx == null) return;
    final word = wordRangeAt(_plain, idx);
    if (word == null) return;
    _dragging = true;
    _anchorWordStart = word[0];
    _anchorWordEnd = word[1];
    _setLocalPreview(word[0], word[1]);
  }

  void _onPanUpdate(DragUpdateDetails d) {
    if (!widget.paintMode || !_dragging) return;
    final a0 = _anchorWordStart;
    final a1 = _anchorWordEnd;
    if (a0 == null || a1 == null) return;
    final idx = _indexForGlobal(d.globalPosition);
    if (idx == null) return;
    final snapped = wordSnappedSelection(
      plain: _plain,
      anchorStart: a0,
      anchorEnd: a1,
      extentIndex: idx,
    );
    if (snapped == null) return;
    _setLocalPreview(snapped[0], snapped[1]);
  }

  void _onPanEnd(DragEndDetails _) {
    if (!widget.paintMode || !_dragging) return;
    final start = _previewStart ?? _anchorWordStart;
    final end = _previewEnd ?? _anchorWordEnd;
    _dragging = false;
    _anchorWordStart = null;
    _anchorWordEnd = null;
    if (start == null || end == null) return;
    final clamped = clampCharRange(start, end, _plain.length);
    if (clamped == null) {
      widget.onPaintCancel?.call();
      return;
    }
    widget.onPaintCommitted?.call(clamped[0], clamped[1]);
  }

  void _onPanCancel() {
    // Arena cancel must not exit highlighter — only drop the in-progress stroke.
    if (!_dragging) return;
    _dragging = false;
    _anchorWordStart = null;
    _anchorWordEnd = null;
    if (_localPreviewStart != null || _localPreviewEnd != null) {
      setState(() {
        _localPreviewStart = null;
        _localPreviewEnd = null;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final spans = buildAnnotatedSpans(
      widget.html,
      widget.style,
      ranges: _rangesForPaint(),
      plainMetrics: widget.paintMode,
    );
    final text = Text.rich(
      TextSpan(style: widget.style, children: spans),
      key: _textKey,
      textAlign: widget.textAlign,
    );
    if (!widget.paintMode) return text;
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onPanStart: _onPanStart,
      onPanUpdate: _onPanUpdate,
      onPanEnd: _onPanEnd,
      onPanCancel: _onPanCancel,
      child: text,
    );
  }
}
