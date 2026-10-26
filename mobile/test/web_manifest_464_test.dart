import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('installed app covers the whole origin so Chrome keeps folder grants', () {
    final m = jsonDecode(File('web/manifest.json').readAsStringSync()) as Map;
    expect(m['scope'], '/');
    expect(m['start_url'], '.');
    expect(m.containsKey('id'), isFalse);
  });
}
