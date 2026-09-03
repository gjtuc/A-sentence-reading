import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/services/figure_disk_cache.dart';

void main() {
  late Directory tmp;
  late FigureDiskCache cache;

  setUp(() async {
    tmp = await Directory.systemTemp.createTemp('asr_fig_disk_');
    cache = FigureDiskCache(rootResolver: () async => tmp);
    cache.bindUid('user_test_01');
  });

  tearDown(() async {
    if (await tmp.exists()) {
      await tmp.delete(recursive: true);
    }
  });

  test('write read purge roundtrip', () async {
    final bytes = Uint8List.fromList(List<int>.generate(64, (i) => i));
    final ok = await cache.writeBytes(
      'abcd1234ef',
      figureId: 'fig-0001',
      bytes: bytes,
      contentHash: 'aa' * 16,
    );
    expect(ok, isTrue);
    final got = await cache.readBytes('abcd1234ef', 'fig-0001');
    expect(got, bytes);
    final url = await cache.readDataUrl('abcd1234ef', 'fig-0001');
    expect(url, startsWith('data:image/png;base64,'));
    expect(await cache.filledCount('abcd1234ef', ['fig-0001', 'fig-0002']), 1);
    await cache.purge('abcd1234ef');
    expect(await cache.readBytes('abcd1234ef', 'fig-0001'), isNull);
  });

  test('content_hash mismatch wipes dir', () async {
    final bytes = Uint8List.fromList([1, 2, 3, 4, 5]);
    await cache.writeBytes(
      'abcd1234ef',
      figureId: 'fig-0001',
      bytes: bytes,
      contentHash: 'hash_old_aaaaaaaa',
    );
    final wiped = await cache.ensureContentHash(
      'abcd1234ef',
      'hash_new_bbbbbbbb',
    );
    expect(wiped, isTrue);
    expect(await cache.readBytes('abcd1234ef', 'fig-0001'), isNull);
  });

  test('unbound uid is no-op', () async {
    cache.bindUid(null);
    final ok = await cache.writeBytes(
      'abcd1234ef',
      figureId: 'fig-0001',
      bytes: Uint8List.fromList([9, 9, 9]),
    );
    expect(ok, isFalse);
  });

  test('dataUrl encode decode helpers', () {
    final bytes = Uint8List.fromList([10, 20, 30]);
    final url = figureDataUrlFromBytes(bytes);
    expect(figureBytesFromDataUrl(url), bytes);
    expect(figureCacheSafeToken(r'fig/../x'), 'fig____x');
  });

  test('atomic write leaves readable file', () async {
    final bytes = Uint8List.fromList(List<int>.filled(100, 7));
    await cache.writeBytes(
      'zzzz9999aa',
      figureId: 'table-1',
      bytes: bytes,
    );
    final m = await cache.loadManifest('zzzz9999aa');
    expect(m, isNotNull);
    expect(m!.figures.containsKey('table-1'), isTrue);
    expect(m.figures['table-1']!.bytes, 100);
  });
}
