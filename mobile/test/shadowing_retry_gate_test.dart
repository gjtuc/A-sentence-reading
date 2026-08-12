/// design/120 — replay gate unit tests.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/shadowing_retry_gate.dart';

void main() {
  test('empty path cannot replay', () {
    expect(canReplayShadowingTake(null), isFalse);
    expect(canReplayShadowingTake(''), isFalse);
    expect(canReplayShadowingTake('   '), isFalse);
  });

  test('non-empty path can replay', () {
    expect(canReplayShadowingTake('/tmp/asr_shadow_1.m4a'), isTrue);
  });
}
