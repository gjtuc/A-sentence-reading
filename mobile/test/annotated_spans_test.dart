import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/annotation_models.dart';
import 'package:sentence_reading/api/rich_sentence.dart';

void main() {
  test('buildAnnotatedSpans whole-sentence yellow', () {
    const html = 'The catalytic activity was measured.';
    final spans = buildAnnotatedSpans(
      html,
      const TextStyle(fontSize: 16),
      ranges: const [
        AnnotationRange(
          start: 0,
          end: 999,
          background: Color(0xFFFFF59D),
        ),
      ],
    );
    expect(spans, isNotEmpty);
    final hasBg = spans.any((s) {
      if (s is TextSpan) {
        return s.style?.backgroundColor != null;
      }
      return false;
    });
    expect(hasBg, isTrue);
  });

  test('buildAnnotatedSpans with sub tag', () {
    const html = 'H<sub>2</sub>O is water.';
    final spans = buildAnnotatedSpans(
      html,
      const TextStyle(fontSize: 16),
      ranges: const [
        AnnotationRange(
          start: 0,
          end: 20,
          background: Color(0xFFC8E6C9),
        ),
      ],
    );
    expect(spans.length, greaterThan(1));
  });
}
