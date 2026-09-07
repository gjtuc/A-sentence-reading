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

  test('buildAnnotatedSpans preserves spaces at highlight edges', () {
    const html = 'The catalytic activity was measured.';
    final spans = buildAnnotatedSpans(
      html,
      const TextStyle(fontSize: 16),
      ranges: const [
        AnnotationRange(start: 4, end: 13, background: Color(0xFFFFF59D)),
      ],
    );
    final text = spans.whereType<TextSpan>().map((s) => s.text ?? '').join();
    expect(text, html);
    expect(text.contains('The catalytic'), isTrue);
    expect(text.contains('catalytic activity'), isTrue);
  });

  test('plainMetrics empty ranges matches length with a preview range', () {
    // Sentences with <sup> take the rich path when ranges are empty; the first
    // paint preview must not change plain length / layout path (0.3.172).
    const html =
        'low surface area of 7 m<sup>2</sup> g<sup>−1</sup>.';
    final base = const TextStyle(fontSize: 16);
    final plain = plainFromRichHtml(html);
    final armed = buildAnnotatedSpans(html, base, plainMetrics: true);
    final preview = buildAnnotatedSpans(
      html,
      base,
      plainMetrics: true,
      ranges: [
        AnnotationRange(
          start: 0,
          end: plain.indexOf(' ') + 1,
          background: const Color(0xFFFFF59D),
        ),
      ],
    );
    String join(List<InlineSpan> spans) =>
        spans.whereType<TextSpan>().map((s) => s.text ?? '').join();
    expect(join(armed), plain);
    expect(join(preview), plain);
  });
}
