/// design/117 — one-finger-only figure swipe gate.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/figure_swipe_gate.dart';

void main() {
  test('one finger at 1x allows swipe', () {
    expect(
      allowFigureSwipeAfterPan(maxPointerCount: 1, scale: 1.0),
      isTrue,
    );
  });

  test('two fingers at 1x blocks swipe (pinch-out residual)', () {
    // WHY: user pinch-zooms out to identity while fingers still down.
    expect(
      allowFigureSwipeAfterPan(maxPointerCount: 2, scale: 1.0),
      isFalse,
    );
  });

  test('one finger while still zoomed blocks swipe', () {
    expect(
      allowFigureSwipeAfterPan(maxPointerCount: 1, scale: 1.5),
      isFalse,
    );
  });

  test('zero pointers fail-closed', () {
    expect(
      allowFigureSwipeAfterPan(maxPointerCount: 0, scale: 1.0),
      isFalse,
    );
  });
}
