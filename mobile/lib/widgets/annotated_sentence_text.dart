import 'package:flutter/material.dart';

import '../api/annotation_models.dart';
import '../api/rich_sentence.dart';

/// Sentence body with highlight overlays (design/166).
class AnnotatedSentenceText extends StatelessWidget {
  const AnnotatedSentenceText({
    super.key,
    required this.html,
    required this.style,
    this.annotations = const [],
    this.textAlign = TextAlign.start,
  });

  final String html;
  final TextStyle style;
  final List<AnnotationEvent> annotations;
  final TextAlign textAlign;

  @override
  Widget build(BuildContext context) {
    final plainLen = plainFromRichHtml(html).length;
    final ranges = <AnnotationRange>[];
    for (final ev in annotations) {
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
    final spans = buildAnnotatedSpans(html, style, ranges: ranges);
    return Text.rich(
      TextSpan(style: style, children: spans),
      textAlign: textAlign,
    );
  }
}
