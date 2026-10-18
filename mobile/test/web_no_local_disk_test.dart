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
import 'package:sentence_reading/services/disk_fs.dart';
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
  browserDiskMain();
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

const _sessionBody = '{"session_id":"ses_disk","cache_id":"abcd1234",'
    '"title":"Paper A","sentences":[{"id":"s0","text":"First sentence.",'
    '"section":"results"},{"id":"s1","text":"Second sentence.",'
    '"section":"results"}],"figures":[],"sentence_index":0,"figure_index":0}';

/// A server that still holds one paper for handoff until [wipe] is set.
class _HandoffServer {
  bool wipe = false;
  bool fail = false;
  int acks = 0;
  int opens = 0;

  AsrClient client(MemorySessionStore store) {
    final session = utf8.encode(_sessionBody);
    return AsrClient(
      sessionStore: store,
      httpClient: MockClient((request) async {
        final path = request.url.path;
        Map<String, dynamic>? json;
        if (path.endsWith('/api/auth/status')) {
          json = {'ok': true, 'user': {'uid': 'u1', 'email': 'a@b.c'}};
        } else if (path.endsWith('/api/status')) {
          json = {'ok': true, 'paper_local_sot': true, 'paper_handoff': true};
        } else if (path.endsWith('/handoff-manifest')) {
          json = {
            'ok': true,
            'content_hash': '',
            'artifact_gen': 'g1',
            'title': 'Paper A',
            'files': {
              'session.json': {'size': session.length, 'sha256': paperDiskSha256Hex(session)},
            },
          };
        } else if (path.endsWith('/handoff/file')) {
          return http.Response.bytes(session, 200);
        } else if (path.endsWith('/handoff/ack') || path.endsWith('/handoff-ack')) {
          acks += 1;
          json = {'ok': true, 'wiped': true};
        } else if (path.endsWith('/open')) {
          opens += 1;
          return http.Response('{}', 404);
        } else if (path.endsWith('/api/cache/papers')) {
          if (fail) return http.Response('{"ok":false}', 503);
          json = {
            'ok': true,
            'papers': [
              if (!wipe) {'id': 'abcd1234', 'title': 'Paper A'},
            ],
          };
        }
        if (json == null) return http.Response('{}', 404);
        return http.Response(
          jsonEncode(json),
          200,
          headers: {'content-type': 'application/json'},
        );
      }),
    );
  }
}

void browserDiskMain() {
  group('design/409 browser storage', () {
    setUp(() {
      debugBrowserDisk = MemoryDiskFs();
    });

    tearDown(() {
      debugBrowserDisk = null;
    });

    test('the paper store keeps papers in browser storage, not app folders', () async {
      final store = PaperDiskStore()..bindUid('u1');
      expect(await store.uidRoot(), isNull);
      expect(await store.paperDir('abcd1234'), isNull);
      expect(await store.localSourcePath('abcd1234'), isNull);

      expect(
        await store.writeSessionJson('abcd1234', jsonDecode(_sessionBody) as Map<String, dynamic>),
        isTrue,
      );
      await store.upsertIndex(
        PaperDiskIndexEntry(id: 'abcd1234', title: 'Paper A', updatedAt: '2026-10-16T00:00:00Z'),
        caller: 'test',
      );
      expect(await store.hasSession('abcd1234'), isTrue);
      expect((await store.loadSessionJson('abcd1234'))?['title'], 'Paper A');
      expect((await store.listIndex()).map((e) => e.id), ['abcd1234']);
      expect(await store.listChildDirNames(), ['abcd1234']);

      final fs = debugBrowserDisk! as MemoryDiskFs;
      expect(fs.files.keys.where((k) => k.endsWith('.part')), isEmpty);

      final other = PaperDiskStore()..bindUid('u2');
      expect(await other.listIndex(), isEmpty);

      await store.purge('abcd1234');
      expect(await store.hasSession('abcd1234'), isFalse);
      expect(await store.listIndex(), isEmpty);
    });

    test('the web takes a copy without the ACK, and keeps it after the phone wipes the server',
        () async {
      final server = _HandoffServer();
      final sessions = MemorySessionStore();
      await sessions.writeToken('tok');
      final library = LibraryController(
        client: server.client(sessions),
        draftStore: MemoryUploadDraftStore(),
      )..bindFigureDiskUid('u1');

      await library.refresh();
      for (var i = 0; i < 50; i++) {
        if (await library.paperDiskStore.hasSession('abcd1234')) break;
        await Future<void>.delayed(const Duration(milliseconds: 20));
      }
      expect(await library.paperDiskStore.hasSession('abcd1234'), isTrue);
      expect(server.acks, 0, reason: 'an ACK would wipe the paper before the phone pulls it');

      server.wipe = true;
      await library.refresh();
      expect(library.error, isNull);
      expect(library.papers.map((p) => p.id), ['abcd1234']);

      final opened = await library.open(library.papers.first);
      expect(library.error, isNull);
      expect(opened?.sentenceCount, 2);
      expect(server.opens, 0, reason: 'a stored paper opens from browser storage');
    });

    test('design/413 a list that failed to load deletes nothing', () async {
      final server = _HandoffServer();
      final sessions = MemorySessionStore();
      await sessions.writeToken('tok');
      final first = LibraryController(
        client: server.client(sessions),
        draftStore: MemoryUploadDraftStore(),
      )..bindFigureDiskUid('u1');
      await first.refresh();
      for (var i = 0; i < 50; i++) {
        if (await first.paperDiskStore.hasSession('abcd1234')) break;
        await Future<void>.delayed(const Duration(milliseconds: 20));
      }
      expect(await first.paperDiskStore.hasSession('abcd1234'), isTrue);

      // The tab reopened while the server was slow: nothing is listed yet.
      server.fail = true;
      final reopened = LibraryController(
        client: server.client(sessions),
        draftStore: MemoryUploadDraftStore(),
      )..bindFigureDiskUid('u1');
      await reopened.refresh();
      await Future<void>.delayed(const Duration(milliseconds: 200));
      expect(reopened.papers, isEmpty);
      expect(await reopened.paperDiskStore.hasSession('abcd1234'), isTrue);

      // Even a sweep run against the empty list keeps what the device indexed.
      await reopened.sweepLocalResidues(trigger: 'test');
      expect(await reopened.paperDiskStore.hasSession('abcd1234'), isTrue);

      server
        ..fail = false
        ..wipe = true;
      await reopened.refresh();
      expect(reopened.papers.map((p) => p.id), ['abcd1234']);
    });
  });
}
