// design/408 - the web build has no app folders. Without a mock, path_provider
// throws MissingPluginException here exactly as it does in the browser, so a
// store that still asks for its folder fails this file.

import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sentence_reading/api/client.dart';
import 'package:sentence_reading/api/pdf_advisory_cache_store.dart';
import 'package:sentence_reading/api/pdf_hash_cache_store.dart';
import 'package:sentence_reading/api/session_store.dart';
import 'package:sentence_reading/api/title_switch_store.dart';
import 'package:sentence_reading/api/upload_draft_store.dart';
import 'package:sentence_reading/practice_skill/skill_evidence_store.dart';
import 'package:sentence_reading/services/documents_mirror_store.dart';
import 'package:sentence_reading/services/figure_disk_cache.dart';
import 'package:sentence_reading/services/figure_png_cache.dart';
import 'package:sentence_reading/services/local_disk.dart';
import 'package:sentence_reading/services/notes_local_archive.dart';
import 'package:sentence_reading/services/paper_disk_store.dart';
import 'package:sentence_reading/services/paper_edit_stash.dart';
import 'package:sentence_reading/services/shadowing_disk_store.dart';
import 'package:sentence_reading/services/tts_audio_cache.dart';
import 'package:sentence_reading/state/library_controller.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
    debugNoLocalDisk = true;
  });

  tearDown(() {
    debugNoLocalDisk = false;
  });

  test('control: with a disk the paper store asks path_provider and fails here', () async {
    debugNoLocalDisk = false;
    final store = PaperDiskStore()..bindUid('u1');
    await expectLater(store.uidRoot(), throwsA(isA<MissingPluginException>()));
  });

  test('paper and shadowing stores read as empty', () async {
    final paper = PaperDiskStore()..bindUid('u1');
    expect(paper.isBound, isTrue);
    expect(await paper.uidRoot(), isNull);
    expect(await paper.paperDir('abc'), isNull);
    expect(await paper.listIndex(), isEmpty);
    expect(await paper.listChildDirNames(), isEmpty);
    expect(await paper.hasSession('abc'), isFalse);
    expect(await paper.loadSessionJson('abc'), isNull);
    expect(await paper.loadManifest('abc'), isNull);

    final shadow = ShadowingDiskStore()..bindUid('u1');
    expect(await shadow.uidRoot(), isNull);
    expect(await shadow.loadChunkPlanJson('abc'), isNull);
  });

  test('figure caches keep nothing', () async {
    final disk = FigureDiskCache()..bindUid('u1');
    expect(await disk.listChildDirNames(), isEmpty);
    expect(await disk.paperDir('abc'), isNull);
    expect(await disk.loadManifest('abc'), isNull);

    final png = FigurePngCache();
    await png.write('a.png', const [1, 2, 3]);
    expect(await png.read('a.png'), isNull);

    final tts = TtsAudioCache();
    await tts.write('k', const [1, 2, 3]);
    expect(await tts.read('k'), isNull);
  });

  test('notes archive and picker caches keep nothing', () async {
    final notes = NotesLocalArchive()..bindUid('u1');
    expect(await notes.saveStoreJson({'a': 1}), isFalse);
    expect(await notes.loadStoreJson(), isNull);

    final titles = TitleSwitchStore();
    await titles.bindUid('u1');
    await titles.put(
      docUri: 'content://x',
      sizeBytes: 10,
      lastModifiedMs: 1,
      boxTitle: 'b',
      verifiedTitle: 'v',
      shown: 'b',
    );

    final hashes = PdfHashCacheStore();
    await hashes.bindUid('u1');
    await hashes.put(
      docUri: 'content://x',
      sizeBytes: 10,
      lastModifiedMs: 1,
      contentHash: 'a' * 64,
    );
    await hashes.lookup(docUri: 'content://x', sizeBytes: 10, lastModifiedMs: 1);

    final advisory = PdfAdvisoryCacheStore();
    await advisory.bindUid('u1');
    expect(
      await advisory.lookup(docUri: 'content://x', sizeBytes: 10, lastModifiedMs: 1),
      isNull,
    );
  });

  test('edit stash holds no source and refuses to save one', () async {
    final stash = PaperEditStash();
    expect(await stash.readMeta('abc'), isNull);
    expect(await stash.hasSource('abc'), isFalse);
    expect(await stash.sourcePath('abc'), isNull);
    expect(await stash.readSourceBytes('abc'), isNull);
    expect(await stash.readPagePreview('abc', 0), isNull);
    await stash.writePagePreview('abc', 0, Uint8List.fromList(const [1]));
    await stash.invalidatePreviews('abc');
    await stash.purge('abc');
    await stash.purgeAll();
    await stash.purgeOrphans({'abc'});
    await expectLater(
      stash.saveSource(
        cacheId: 'abc',
        bytes: Uint8List.fromList(const [1]),
        filename: 'a.pdf',
      ),
      throwsA(
        isA<PaperStashException>().having((e) => e.code, 'code', 'no_local_disk'),
      ),
    );
  });

  test('skill evidence queue stays empty', () async {
    final q = SkillEvidenceStore();
    await q.bindUid('u1');
    await q.append({'kind': 'x'});
    expect(await q.pendingCount(), 0);
    expect(await q.peek(10), isEmpty);
    await q.ack(1);
    await q.clearAll();
  });

  test('documents mirror stays unbound and never calls its channel', () async {
    final mirror = DocumentsMirrorStore(
      paperDisk: PaperDiskStore()..bindUid('u1'),
      shadowDisk: ShadowingDiskStore()..bindUid('u1'),
    )..bindUid('u1');
    expect(mirror.isBound, isFalse);
    expect(await mirror.hideFromGalleryOnce(), isFalse);
    expect(await mirror.tryEmptyGateRestore(), 0);
    expect(await mirror.mirrorPaper('abc'), isFalse);
    expect(await mirror.deletePaper('abc'), isFalse);
    await mirror.flushCursors();
  });

  libraryMain();
}

Future<AsrClient> _webClient() async {
  final store = MemorySessionStore();
  await store.writeToken('tok');
  return AsrClient(
    sessionStore: store,
    httpClient: MockClient((request) async {
      final path = request.url.path;
      if (path.endsWith('/api/auth/status')) {
        return http.Response(
          '{"ok":true,"user":{"uid":"u1","email":"a@b.c"}}',
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (path.endsWith('/api/cache/papers/abcd1234/open')) {
        return http.Response(
          jsonEncode({
            'session_id': 'ses_web',
            'cache_id': 'abcd1234',
            'title': 'Paper A',
            'sentences': [
              {'id': 's0', 'text': 'First sentence.', 'section': 'results'},
              {'id': 's1', 'text': 'Second sentence.', 'section': 'results'},
            ],
            'figures': [],
            'sentence_index': 0,
            'figure_index': 0,
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (path.endsWith('/api/cache/papers')) {
        return http.Response(
          '{"ok":true,"papers":[{"id":"abcd1234","title":"Paper A"}]}',
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      return http.Response('{}', 404);
    }),
  );
}

Future<LibraryController> _boundLibrary() async {
  final client = await _webClient();
  final library = LibraryController(
    client: client,
    draftStore: MemoryUploadDraftStore(),
  )..bindFigureDiskUid('u1');
  await library.refresh();
  return library;
}

void libraryMain() {
  test('control: a bound library with a disk shows the web error', () async {
    debugNoLocalDisk = false;
    Object? caught;
    await runZonedGuarded(() async {
      final library = await _boundLibrary();
      caught ??= library.error;
    }, (e, _) => caught ??= e);
    expect('$caught', contains('MissingPluginException'));
  });

  test('a bound library lists and opens a server paper without a disk', () async {
    final errors = <Object>[];
    await runZonedGuarded(() async {
      final library = await _boundLibrary();
      expect(library.error, isNull);
      expect(library.papers.map((p) => p.id), ['abcd1234']);
      final opened = await library.open(library.papers.first);
      expect(library.error, isNull);
      expect(opened?.sentenceCount, 2);
      await Future<void>.delayed(const Duration(milliseconds: 200));
    }, (e, _) => errors.add(e));
    expect(errors, isEmpty);
  });
}
