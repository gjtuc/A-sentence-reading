import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/annotation_models.dart';
import 'package:sentence_reading/api/figure_ink_models.dart';

void main() {
  test('inkEventIdNearPoint finds close stroke', () {
    final ev = AnnotationEvent(
      id: 'a1',
      at: '2026-01-01T00:00:00Z',
      kind: 'ink',
      paths: [
        {
          'points': [
            [0.1, 0.1],
            [0.5, 0.5],
          ],
        },
      ],
    );
    expect(
      inkEventIdNearPoint(events: [ev], nx: 0.3, ny: 0.3, threshold: 0.05),
      'a1',
    );
    expect(
      inkEventIdNearPoint(events: [ev], nx: 0.9, ny: 0.9, threshold: 0.05),
      isNull,
    );
  });

  test('figureInkPalette has six colors', () {
    expect(figureInkPalette, hasLength(6));
  });
}
