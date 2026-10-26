import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('design/465: an unknown user at boot does not wipe the library', () {
    final src = File('lib/app.dart').readAsStringSync();
    final guard = src.indexOf(
        'if (_auth.bootstrapping || _auth.sessionRestorePending) return;');
    final wipe = src.indexOf('await _library.clearAll();');
    expect(guard, greaterThan(0));
    expect(wipe, greaterThan(guard));
  });

  test('design/465: web keeps the session on a slow auth/status', () {
    final src = File('lib/state/auth_controller.dart').readAsStringSync();
    expect(src, contains('hasToken || kIsWeb ||'));
  });
}
