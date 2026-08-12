/// design/118 — pinch scale amplification unit tests.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/figure_pinch_sensitivity.dart';

void main() {
  test('identity raw stays 1', () {
    expect(amplifyFigurePinchScale(rawScale: 1.0), 1.0);
  });

  test('zoom-in is stronger than raw (확실히 체감)', () {
    const raw = 1.25;
    final amp = amplifyFigurePinchScale(rawScale: raw);
    expect(amp, greaterThan(raw));
    expect(amp, greaterThan(1.4)); // 1.25^1.85 ≈ 1.51
  });

  test('zoom-out is stronger than raw', () {
    const raw = 0.8;
    final amp = amplifyFigurePinchScale(rawScale: raw);
    expect(amp, lessThan(raw));
  });

  test('non-finite / non-positive fail closed to 1', () {
    expect(amplifyFigurePinchScale(rawScale: double.nan), 1.0);
    expect(amplifyFigurePinchScale(rawScale: double.infinity), 1.0);
    expect(amplifyFigurePinchScale(rawScale: 0), 1.0);
    expect(amplifyFigurePinchScale(rawScale: -1), 1.0);
  });

  test('bad sensitivity falls back to raw', () {
    expect(
      amplifyFigurePinchScale(rawScale: 1.4, sensitivity: 0),
      1.4,
    );
  });

  test('sensitivity constant is clearly > 1', () {
    expect(kFigurePinchSensitivity, greaterThan(1.5));
  });
}
