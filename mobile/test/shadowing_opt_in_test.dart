import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/shadowing_models.dart';
import 'package:sentence_reading/api/shadowing_store.dart';
import 'package:sentence_reading/state/shadowing_controller.dart';

class _MemShadowingStore implements ShadowingStore {
  final Map<String, String> _data = {};

  @override
  Future<String?> readRaw(String? uid) async => _data[shadowingPrefsKey(uid)];

  @override
  Future<void> writeRaw(String? uid, String raw) async {
    _data[shadowingPrefsKey(uid)] = raw;
  }
}

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

  test('shadowing toggle saves when server kill is off', () async {
    final store = _MemShadowingStore();
    final c = ShadowingController(store: store);
    c.setServerAvailable(false);
    await c.bindUid('u1');
    expect(c.enabled, isFalse);

    await c.setEnabled(true);
    expect(c.enabled, isTrue);
    expect(c.error, isNull);

    await c.bindUid('u1');
    expect(c.enabled, isTrue);
  });
}
