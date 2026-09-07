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
          end: 3,
          background: Color(0xFFC8E6C9),
        ),
      ],
    );
    expect(spans, isNotEmpty);
    final hasBg = spans.any(
      (s) => s is TextSpan && s.style?.backgroundColor != null,
    );
    expect(hasBg, isTrue);
  });

  test('buildAnnotatedSpans partial overlap later wins', () {
    const html = 'abcdefghij';
    final spans = buildAnnotatedSpans(
      html,
      const TextStyle(fontSize: 16),
      ranges: const [
        AnnotationRange(start: 0, end: 6, background: Color(0xFFFFF59D)),
        AnnotationRange(start: 3, end: 9, background: Color(0xFFC8E6C9)),
      ],
    );
    expect(spans, isNotEmpty);
    final hasGreen = spans.any((s) {
      if (s is! TextSpan) return false;
      final c = s.style?.backgroundColor;
      if (c == null) return false;
      return c.g > c.r;
    });
    expect(hasGreen, isTrue);
  });
}
