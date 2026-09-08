import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/reading_models.dart';
import 'package:sentence_reading/services/paper_disk_store.dart';

void main() {
  late Directory tmp;
  late PaperDiskStore store;

  setUp(() async {
    tmp = await Directory.systemTemp.createTemp('asr_paper_disk_');
    store = PaperDiskStore(rootResolver: () async => tmp);
    store.bindUid('user_test_185');
  });

  tearDown(() async {
    if (await tmp.exists()) {
      await tmp.delete(recursive: true);
    }
  });

  test('session write load purge roundtrip', () async {
    final ok = await store.writeSessionJson(
      'abcd1234ef',
      {
        'cache_id': 'abcd1234ef',
        'title': 'Hello',
        'sentences': [
          {'id': 's1', 'text': 'One'},
        ],
        'figures': [],
      },
      contentHash: 'aa' * 16,
    );
    expect(ok, isTrue);
    final loaded = await store.loadSessionJson('abcd1234ef');
    expect(loaded?['title'], 'Hello');
    final m = await store.loadManifest('abcd1234ef');
    expect(m, isNotNull);
    expect(m!.files.containsKey('session.json'), isTrue);
    await store.purge('abcd1234ef');
    expect(await store.loadSessionJson('abcd1234ef'), isNull);
  });

  test('figure bytes + index merge', () async {
    final bytes = Uint8List.fromList(List<int>.generate(32, (i) => i));
    await store.writeSessionJson(
      'zzzz9999aa',
      {
        'cache_id': 'zzzz9999aa',
        'title': 'Local Only',
        'sentences': [
          {'id': 's1', 'text': 'x'},
        ],
      },
      contentHash: 'bb' * 16,
    );
    expect(
      await store.writeFigureBytes(
        'zzzz9999aa',
        figureId: 'fig-1',
        bytes: bytes,
        contentHash: 'bb' * 16,
      ),
      isTrue,
    );
    expect(await store.readFigureBytes('zzzz9999aa', 'fig-1'), bytes);
    await store.upsertIndex(
      PaperDiskIndexEntry(
        id: 'zzzz9999aa',
        title: 'Local Only',
        sentenceCount: 1,
        figureCount: 1,
        contentHash: 'bb' * 16,
      ),
    );
    final merged = await store.mergeRemoteWithLocal(const []);
    expect(merged.length, 1);
    expect(merged.first.id, 'zzzz9999aa');
    expect(merged.first.ingestStatus, 'local');
  });

  test('content_hash mismatch wipes', () async {
    await store.writeSessionJson(
      'hashwipe01',
      {'cache_id': 'hashwipe01', 'title': 'T', 'sentences': []},
      contentHash: 'oldhashaaaaaaaaaa',
    );
    final wiped = await store.ensureContentHash(
      'hashwipe01',
      'newhashbbbbbbbbbb',
    );
    expect(wiped, isTrue);
    expect(await store.loadSessionJson('hashwipe01'), isNull);
  });

  test('shadowPersistReadingSession writes session without data urls', () async {
    final png = Uint8List.fromList([137, 80, 78, 71, 13, 10, 26, 10]);
    final dataUrl =
        'data:image/png;base64,${base64Encode(png)}';
    final session = ReadingSession(
      sessionId: 'sess1',
      cacheId: 'shadow001aa',
      title: 'Shadow',
      contentHash: 'cc' * 16,
      sentences: [SentenceView(id: 's1', text: 'Hello')],
      figures: [
        FigureView(id: 'fig-a', imageSrc: dataUrl, caption: 'Cap'),
      ],
    );
    expect(await store.shadowPersistReadingSession(session), isTrue);
    final raw = await store.loadSessionJson('shadow001aa');
    expect(raw?['title'], 'Shadow');
    final figs = raw?['figures'] as List?;
    expect(figs, isNotNull);
    expect((figs!.first as Map)['image_src'], '');
    expect(await store.readFigureBytes('shadow001aa', 'fig-a'), png);
  });

  test('unbound is no-op', () async {
    store.bindUid(null);
    expect(
      await store.writeSessionJson('x', {'cache_id': 'x', 'title': 't'}),
      isFalse,
    );
  });
}
