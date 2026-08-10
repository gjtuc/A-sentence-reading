import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/shadowing_models.dart';

void main() {
  test('shadowing prefs default off and uid key', () {
    expect(parseShadowingEnabledPref(null), isFalse);
    expect(parseShadowingEnabledPref(''), isFalse);
    expect(parseShadowingEnabledPref('garbage'), isFalse);
    expect(parseShadowingEnabledPref('{"enabled":true}'), isTrue);
    expect(parseShadowingEnabledPref('{"enabled":false}'), isFalse);
    expect(shadowingPrefsKey(null), kShadowingPrefsKeyBase);
    expect(shadowingPrefsKey('u1'), 'asr.shadowing.v1.u1');
    expect(shadowingPrefsKey('u1'), isNot(shadowingPrefsKey('u2')));
  });
}
