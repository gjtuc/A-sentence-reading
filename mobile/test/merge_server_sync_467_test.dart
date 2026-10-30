import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

String _body(String src, String head) {
  final at = src.indexOf(head);
  expect(at, greaterThanOrEqualTo(0), reason: head);
  final next = src.indexOf('\n  Future<', at + head.length);
  return src.substring(at, next < 0 ? src.length : next);
}

void main() {
  final src = File('lib/state/library_controller.dart').readAsStringSync();

  test('local merge is also sent to the server before refresh', () {
    // design/492 — the pair merge runs through attachParts.
    final body = _body(src, 'Future<bool> attachParts(');
    final local = body.indexOf("path = 'local'");
    final sync = body.indexOf('await _client.attachParts(entry.id, parts)', local);
    final refresh = body.indexOf("refresh(fresh: false, clearError: false, trigger: 'merge')", local);
    expect(local, greaterThanOrEqualTo(0));
    expect(sync, greaterThan(local));
    expect(refresh, greaterThan(sync));
    expect(body.contains("'server_sync': serverSync"), isTrue);
  });

  test('second local merge drops the old SI part first', () {
    final body = _body(src, 'Future<bool> _mergePartsLocal(');
    expect(body.contains("mainSession['supplementary_merged'] == true"), isTrue);
    expect(
      body.contains("rebuildSi && '\${s['section'] ?? ''}' == 'supplementary'"),
      isTrue,
    );
    expect(
      body.contains("rebuildSi && '\${f['id'] ?? ''}'.trim().startsWith('si-')"),
      isTrue,
    );
    expect(body.contains("'stripped_sent_n': strippedSentN"), isTrue);
  });
}
