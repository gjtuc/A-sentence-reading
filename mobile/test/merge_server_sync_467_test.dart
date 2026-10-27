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
    final body = _body(src, 'Future<bool> mergeSupplementary(PaperEntry entry)');
    final local = body.indexOf("path = 'local'");
    final sync = body.indexOf('await _client.mergeSupplementary(entry.id)', local);
    final refresh = body.indexOf("refresh(fresh: false, clearError: false, trigger: 'merge')", local);
    expect(local, greaterThanOrEqualTo(0));
    expect(sync, greaterThan(local));
    expect(refresh, greaterThan(sync));
    expect(body.contains("'server_sync': serverSync"), isTrue);
  });

  test('second local merge drops the old SI part first', () {
    final body = _body(src, 'Future<bool> _mergeSupplementaryLocal(');
    expect(body.contains("mainSession['supplementary_merged'] == true"), isTrue);
    expect(
      body.contains("priorMerge && '\${s['section'] ?? ''}' == 'supplementary'"),
      isTrue,
    );
    expect(
      body.contains("priorMerge && '\${f['id'] ?? ''}'.trim().startsWith('si-')"),
      isTrue,
    );
    expect(body.contains("'stripped_sent_n': strippedSentN"), isTrue);
  });
}
