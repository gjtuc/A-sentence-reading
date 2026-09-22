/// Rubber-band page swipe stays on the finger, then flies past the screen.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/widgets/swipe_motion.dart';

void main() {
  test('a short drag almost follows the finger', () {
    final moved = rubberBandOffset(40, 400);
    expect(moved, greaterThan(30));
    expect(moved, lessThan(40));
  });

  test('a long drag resists more than it follows', () {
    final moved = rubberBandOffset(400, 400);
    expect(moved, greaterThan(0));
    expect(moved, lessThan(400));
  });

  test('the band keeps the finger direction', () {
    expect(rubberBandOffset(-80, 400), lessThan(0));
    expect(rubberBandOffset(0, 400), 0);
  });

  test('a committed swipe flies off the side the finger left', () {
    expect(flingTarget(-20, 400), closeTo(-460, 0.01));
    expect(flingTarget(20, 400), closeTo(460, 0.01));
  });
}
