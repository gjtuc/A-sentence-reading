/// Crop drag stays as a page rectangle until body/caption assign.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/services/figure_edit_geometry.dart';
import 'package:sentence_reading/services/figure_edit_session.dart';

void main() {
  test('fitted page is centered in a taller view', () {
    final rect = fittedContainRect(const Size(400, 800), 612 / 792);
    expect(rect.left, 0);
    expect(rect.width, 400);
    expect(rect.height, lessThan(800));
    expect(rect.top, greaterThan(0));
    expect(rect.center.dy, closeTo(400, 0.01));
  });

  test('fitted page is centered in a wider view', () {
    final rect = fittedContainRect(const Size(800, 400), 612 / 792);
    expect(rect.top, 0);
    expect(rect.height, 400);
    expect(rect.width, lessThan(800));
    expect(rect.left, greaterThan(0));
  });

  test('drag on the page is page-normalized and kept', () {
    const page = Size(300, 400);
    final rect = normRectFromDrag(
      start: const Offset(30, 40),
      end: const Offset(150, 200),
      size: page,
    );
    expect(rect.left, closeTo(0.1, 0.001));
    expect(rect.top, closeTo(0.1, 0.001));
    expect(rect.right, closeTo(0.5, 0.001));
    expect(rect.bottom, closeTo(0.5, 0.001));
    expect(cropDragKept(rect, page), isTrue);
  });

  test('a tap is not kept as a crop', () {
    const page = Size(300, 400);
    final rect = normRectFromDrag(
      start: const Offset(40, 40),
      end: const Offset(44, 43),
      size: page,
    );
    expect(cropDragKept(rect, page), isFalse);
  });

  test('manual crop is stored and its id is returned', () {
    final session = FigureEditSession(
      cacheId: 'c',
      layoutMap: {
        'pages': [
          {'width_pt': 100, 'height_pt': 200},
        ],
        'boxes': <Map<String, dynamic>>[],
      },
      slots: [
        {'key': 'fig:1', 'kind': 'fig'},
      ],
    );
    const rect = NormRect(left: 0.1, top: 0.2, right: 0.4, bottom: 0.5);
    final id = session.addManualBox(
      pageIndex: 0,
      rect: rect,
      kind: 'figure_caption',
    );
    expect(id, 'user-crop-1');
    expect(session.dirty, isTrue);
    final box = session.boxes.single;
    expect(box['id'], id);
    expect(box['kind'], 'figure_caption');
    expect(box['source'], 'user');
    expect((box['rect'] as Map)['x0'], 10);
    expect((box['rect'] as Map)['y0'], 40);
    expect((box['rect'] as Map)['x1'], 40);
    expect((box['rect'] as Map)['y1'], 100);
  });

  test('a pan in the middle does not turn the page', () {
    expect(
      panEdgePageTurn(
        atLeftEdge: false,
        atRightEdge: false,
        dx: -80,
        dy: 0,
        vx: -900,
        vy: 0,
        pointerCount: 1,
        pulledPastLeft: false,
        pulledPastRight: false,
      ),
      PanEdgeTurn.none,
    );
  });

  test('a further swipe at the right edge turns to the next page', () {
    expect(
      panEdgePageTurn(
        atLeftEdge: false,
        atRightEdge: true,
        dx: -4,
        dy: 2,
        vx: -700,
        vy: 40,
        pointerCount: 1,
        pulledPastLeft: false,
        pulledPastRight: true,
      ),
      PanEdgeTurn.next,
    );
  });

  test('a further swipe at the left edge turns to the previous page', () {
    expect(
      panEdgePageTurn(
        atLeftEdge: true,
        atRightEdge: false,
        dx: 10,
        dy: 0,
        vx: 800,
        vy: 0,
        pointerCount: 1,
        pulledPastLeft: true,
        pulledPastRight: false,
      ),
      PanEdgeTurn.previous,
    );
  });

  test('pulling inward from the right edge stays on the page', () {
    expect(
      panEdgePageTurn(
        atLeftEdge: false,
        atRightEdge: true,
        dx: 70,
        dy: 0,
        vx: 800,
        vy: 0,
        pointerCount: 1,
        pulledPastLeft: false,
        pulledPastRight: false,
      ),
      PanEdgeTurn.none,
    );
  });

  test('a fitted page turns with the swipe direction', () {
    expect(
      panEdgePageTurn(
        atLeftEdge: true,
        atRightEdge: true,
        dx: -60,
        dy: 0,
        vx: -200,
        vy: 0,
        pointerCount: 1,
        pulledPastLeft: false,
        pulledPastRight: false,
      ),
      PanEdgeTurn.next,
    );
  });

  test('a pinch does not turn the page', () {
    expect(
      panEdgePageTurn(
        atLeftEdge: true,
        atRightEdge: true,
        dx: -80,
        dy: 0,
        vx: -900,
        vy: 0,
        pointerCount: 2,
        pulledPastLeft: false,
        pulledPastRight: true,
      ),
      PanEdgeTurn.none,
    );
  });
}
