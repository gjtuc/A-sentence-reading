// design/410 — phone <-> web near sync protocol, in memory.
import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/progress_store.dart';
import 'package:sentence_reading/services/disk_fs.dart';
import 'package:sentence_reading/services/local_disk.dart';
import 'package:sentence_reading/services/near_library_local.dart';
import 'package:sentence_reading/services/near_relay.dart';
import 'package:sentence_reading/services/near_sync.dart';
import 'package:sentence_reading/services/paper_disk_store.dart';
import 'package:sentence_reading/services/shadowing_disk_store.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _End implements NearPipe {
  _End(this._out);

  final StreamController<Uint8List> _out;
  final _in = StreamController<Uint8List>();
  var sent = 0;
  int? cutAfter;

  @override
  Stream<Uint8List> get frames => _in.stream;

  @override
  Future<void> send(Uint8List frame) async {
    if (_out.isClosed || _in.isClosed) throw StateError('closed');
    sent += 1;
    if (cutAfter != null && sent > cutAfter!) {
      unawaited(_out.close());
      unawaited(_in.close());
      return;
    }
    final copy = Uint8List.fromList(frame);
    scheduleMicrotask(() {
      if (!_out.isClosed) _out.add(copy);
    });
  }
}

(_End, _End) _pair() {
  final aIn = StreamController<Uint8List>();
  final bIn = StreamController<Uint8List>();
  final a = _End(bIn);
  final b = _End(aIn);
  void feed(StreamController<Uint8List> to, Uint8List f) {
    if (!to.isClosed) to.add(f);
  }

  aIn.stream.listen((f) => feed(a._in, f), onDone: () => a._in.isClosed ? null : a._in.close());
  bIn.stream.listen((f) => feed(b._in, f), onDone: () => b._in.isClosed ? null : b._in.close());
  return (a, b);
}

class _Mem implements NearLocal {
  final papersHeld = <String, NearPaper>{};
  final packs = <String, Map<String, Uint8List>>{};
  final rows = <String, Map<String, dynamic>>{};
  var stored = 0;

  void add(String id, Map<String, Uint8List> files, {String title = ''}) {
    papersHeld[id] = NearPaper(id: id, title: title.isEmpty ? 'T $id' : title, hash: 'h$id');
    packs[id] = files;
  }

  @override
  Future<List<NearPaper>> papers() async => papersHeld.values.toList();

  @override
  Future<Map<String, Uint8List>> pack(String id) async => packs[id] ?? {};

  @override
  Future<bool> store(NearPaper paper, Map<String, Uint8List> files) async {
    await Future<void>.delayed(const Duration(milliseconds: 2));
    papersHeld[paper.id] = paper;
    packs[paper.id] = files;
    stored += 1;
    return true;
  }

  final extras = <String, Map<String, Uint8List>>{};

  @override
  Future<Map<String, List<String>>> extraNames() async => {
        for (final e in extras.entries) e.key: (e.value.keys.toList()..sort()),
      };

  @override
  Future<Map<String, Uint8List>> extraPack(String id, Set<String> skipNames) async => {
        for (final e in (extras[id] ?? const <String, Uint8List>{}).entries)
          if (!skipNames.contains(e.key)) 'shadowing/voice/${e.key}': e.value,
      };

  @override
  Future<int> mergeExtra(String id, Map<String, Uint8List> files) async {
    final into = extras.putIfAbsent(id, () => {});
    var n = 0;
    for (final e in files.entries) {
      final name = e.key.substring('shadowing/voice/'.length);
      if (into.containsKey(name)) continue;
      into[name] = e.value;
      n += 1;
    }
    return n;
  }

  @override
  Future<Map<String, Map<String, dynamic>>> progress() async => rows;

  @override
  Future<int> mergeProgress(Map<String, Map<String, dynamic>> incoming) async {
    var n = 0;
    for (final e in incoming.entries) {
      final mine = rows[e.key];
      if (mine == null || '${e.value['at']}'.compareTo('${mine['at']}') > 0) {
        rows[e.key] = e.value;
        n += 1;
      }
    }
    return n;
  }
}

Uint8List _bytes(int n, int seed) =>
    Uint8List.fromList(List<int>.generate(n, (i) => (i * 31 + seed) & 0xff));

Map<String, Uint8List> _paper(int pdfBytes, int seed) => {
      'session.json': Uint8List.fromList(utf8.encode('{"title":"P$seed","sentences":[]}')),
      'source.pdf': _bytes(pdfBytes, seed),
      'figures/f1.png': _bytes(40 * 1024 + 7, seed + 1),
    };

void main() {
  test('each side gets the papers it lacks, byte for byte', () async {
    final (pa, pb) = _pair();
    final phone = _Mem()..add('p1', _paper(600 * 1024 + 3, 1))..add('both', _paper(10, 9));
    final web = _Mem()..add('w1', _paper(5, 2))..add('both', _paper(10, 9));
    final results = await Future.wait([
      NearSync(pa, phone).run(),
      NearSync(pb, web).run(),
    ]);
    expect(results[0].papersIn, 1);
    expect(results[0].papersOut, 1);
    expect(results[1].papersIn, 1);
    expect(results[1].papersOut, 1);
    expect(phone.papersHeld.keys.toSet(), {'p1', 'w1', 'both'});
    expect(web.papersHeld.keys.toSet(), {'p1', 'w1', 'both'});
    for (final e in phone.packs['p1']!.entries) {
      expect(web.packs['p1']![e.key], e.value, reason: e.key);
    }
    expect(web.papersHeld['p1']!.title, 'T p1');
    expect(web.papersHeld['p1']!.hash, 'hp1');
    expect(phone.stored, 1);
    expect(web.stored, 1);
  });

  test('a paper bigger than the window waits for acks and still arrives whole', () async {
    final (pa, pb) = _pair();
    final phone = _Mem()..add('big', _paper(5 * 1024 * 1024 + 11, 3));
    final web = _Mem();
    final seen = <NearSyncProgress>[];
    final results = await Future.wait([
      NearSync(pa, phone).run(),
      NearSync(pb, web, onProgress: seen.add).run(),
    ]);
    expect(results[1].papersIn, 1);
    expect(web.packs['big']!['source.pdf'], phone.packs['big']!['source.pdf']);
    final total = phone.packs['big']!.values.fold<int>(0, (n, b) => n + b.length);
    expect(seen.last.bytesIn, total);
  });

  test('reading spots cross both ways; the newer one wins', () async {
    final (pa, pb) = _pair();
    final phone = _Mem();
    phone.rows['a'] = {'sentence_index': 9, 'figure_index': 0, 'at': '2026-10-16T10:00:00Z'};
    phone.rows['b'] = {'sentence_index': 1, 'figure_index': 0, 'at': '2026-10-01T00:00:00Z'};
    final web = _Mem();
    web.rows['b'] = {'sentence_index': 4, 'figure_index': 0, 'at': '2026-10-15T00:00:00Z'};
    final results = await Future.wait([
      NearSync(pa, phone).run(),
      NearSync(pb, web).run(),
    ]);
    expect(phone.rows['b']!['sentence_index'], 4);
    expect(web.rows['a']!['sentence_index'], 9);
    expect(web.rows['b']!['sentence_index'], 4);
    expect(results[0].progressRows, 1);
    expect(results[1].progressRows, 1);
  });

  test('nothing to move still finishes', () async {
    final (pa, pb) = _pair();
    final results = await Future.wait([
      NearSync(pa, _Mem()).run(),
      NearSync(pb, _Mem()).run(),
    ]);
    expect(results[0].papersIn + results[1].papersIn, 0);
  });

  test('a cut pipe fails instead of hanging', () async {
    final (pa, pb) = _pair();
    pa.cutAfter = 5;
    final phone = _Mem()..add('big', _paper(1024 * 1024, 4));
    final a = NearSync(pa, phone, quiet: const Duration(seconds: 3)).run();
    final b = NearSync(pb, _Mem(), quiet: const Duration(seconds: 3)).run();
    await expectLater(a, throwsA(isA<NearSyncError>()));
    await expectLater(b, throwsA(isA<NearSyncError>()));
  });

  test('a header with an escaping path is refused', () async {
    final (pa, pb) = _pair();
    final web = NearSync(pb, _Mem(), quiet: const Duration(seconds: 3)).run();
    await pa.send(nearJsonFrame({'t': 'inv', 'papers': [], 'progress': {}}));
    await pa.send(nearJsonFrame({
      't': 'paper',
      'id': 'x',
      'files': [
        {'rel': '../evil', 'size': 1},
      ],
    }));
    await expectLater(
      web,
      throwsA(isA<NearSyncError>().having((e) => e.code, 'code', 'bad_paper')),
    );
  });

  test('nearSafeRel keeps pack paths inside the paper folder', () {
    expect(nearSafeRel('session.json'), isTrue);
    expect(nearSafeRel('figures/f1.png'), isTrue);
    expect(nearSafeRel('/abs'), isFalse);
    expect(nearSafeRel('a/../b'), isFalse);
    expect(nearSafeRel(r'a\b'), isFalse);
    expect(nearSafeRel('C:x'), isFalse);
    expect(nearSafeRel(''), isFalse);
  });

  test('mergeProgressRows: newer spot wins, left-at keeps the later time', () async {
    SharedPreferences.setMockInitialValues({});
    await saveProgressRow(uid: 'u1', cacheId: 'old', sentenceIndex: 2, figureIndex: 0);
    await saveProgressRow(uid: 'u1', cacheId: 'mine', sentenceIndex: 5, figureIndex: 1);
    final mineAt = (await loadProgressRows(uid: 'u1'))['mine']!['at'] as String;
    final n = await mergeProgressRows(uid: 'u1', incoming: {
      'old': {'sentence_index': 7, 'figure_index': 2, 'section_label': 'Intro', 'at': '2999-01-01T00:00:00Z'},
      'mine': {'sentence_index': 0, 'figure_index': 0, 'at': '2000-01-01T00:00:00Z', 'last_read_left_at': '2999-01-01T00:00:00Z'},
      'new': {'sentence_index': 3, 'figure_index': 0, 'at': '2026-10-16T00:00:00Z'},
    });
    expect(n, 3);
    final rows = await loadProgressRows(uid: 'u1');
    expect(rows['old']!['sentence_index'], 7);
    expect(rows['old']!['section_label'], 'Intro');
    expect(rows['mine']!['sentence_index'], 5);
    expect(rows['mine']!['at'], mineAt);
    expect(rows['mine']!['last_read_left_at'], '2999-01-01T00:00:00Z');
    expect(rows['new']!['sentence_index'], 3);
    expect(await mergeProgressRows(uid: 'u1', incoming: {'new': rows['new']!}), 0);
    expect(await loadProgressRows(uid: 'u2'), isEmpty);
  });

  test('two browser-stored libraries sync through the real paper store', () async {
    SharedPreferences.setMockInitialValues({});
    debugNoLocalDisk = true;
    debugBrowserDisk = MemoryDiskFs();
    addTearDown(() {
      debugBrowserDisk = null;
      debugNoLocalDisk = false;
    });
    final phoneDisk = PaperDiskStore()..bindUid('phone');
    final webDisk = PaperDiskStore()..bindUid('web');
    final session = {'title': 'Paper P', 'sentences': [], 'figures': []};
    expect(await phoneDisk.writeSessionJson('abcd1234', session), isTrue);
    expect(await phoneDisk.writeFigureBytes('abcd1234', figureId: 'f1', bytes: _bytes(3000, 5)), isTrue);
    await phoneDisk.upsertIndex(
      PaperDiskIndexEntry(id: 'abcd1234', title: 'Paper P', contentHash: 'cafe'),
      caller: 'test',
    );
    final (pa, pb) = _pair();
    final results = await Future.wait([
      NearSync(pa, LibraryNearLocal(disk: phoneDisk, uid: 'phone')).run(),
      NearSync(pb, LibraryNearLocal(disk: webDisk, uid: 'web')).run(),
    ]);
    expect(results[1].papersIn, 1);
    final got = await webDisk.listIndex();
    expect(got.map((e) => e.id), ['abcd1234']);
    expect(got.single.title, 'Paper P');
    expect(got.single.contentHash, 'cafe');
    expect(await webDisk.hasSession('abcd1234'), isTrue);
    expect(await webDisk.readFigureBytes('abcd1234', 'f1'), _bytes(3000, 5));
  });
  relayMain();
  extrasMain();
}

class _RelayServer {
  final bundles = <String, Uint8List>{};
  var puts = 0;
  var failPuts = 0;

  Future<void> put(String side, int seq, Uint8List b) async {
    await Future<void>.delayed(const Duration(milliseconds: 1));
    if (failPuts > 0) {
      failPuts -= 1;
      throw StateError('put failed');
    }
    puts += 1;
    bundles['$side/$seq'] = Uint8List.fromList(b);
  }

  Future<Uint8List?> take(String side, int seq) async {
    await Future<void>.delayed(const Duration(milliseconds: 1));
    if (seq > 0) bundles.remove('$side/${seq - 1}');
    return bundles['$side/$seq'];
  }
}

void relayMain() {
  group('design/410 relay', () {
    test('a bundle round-trips its frames', () {
      final frames = [Uint8List.fromList([1, 2, 3]), Uint8List(0), Uint8List.fromList([9])];
      final back = decodeRelayBundle(encodeRelayBundle(frames));
      expect(back.length, 3);
      expect(back[0], [1, 2, 3]);
      expect(back[1], isEmpty);
      expect(back[2], [9]);
      expect(() => decodeRelayBundle(Uint8List.fromList([0, 0, 0, 9, 1])), throwsA(isA<NearSyncError>()));
    });

    test('papers and reading spots move through the relay and nothing read stays there', () async {
      final server = _RelayServer()..failPuts = 1;
      NearRelayPipe pipe(bool host) => NearRelayPipe(
            host: host,
            put: server.put,
            take: server.take,
            linger: const Duration(milliseconds: 5),
            idle: const Duration(milliseconds: 5),
          )..start();
      final web = pipe(true);
      final phone = pipe(false);
      final phoneLib = _Mem()..add('big', _paper(3 * 1024 * 1024 + 5, 7));
      phoneLib.rows['big'] = {'sentence_index': 12, 'figure_index': 1, 'at': '2026-10-17T01:00:00Z'};
      final webLib = _Mem()..add('w', _paper(1000, 8));
      final results = await Future.wait([
        NearSync(web, webLib).run(),
        NearSync(phone, phoneLib).run(),
      ]);
      await Future<void>.delayed(const Duration(milliseconds: 50));
      web.close();
      phone.close();
      expect(results[0].papersIn, 1);
      expect(results[1].papersIn, 1);
      expect(webLib.packs['big']!['source.pdf'], phoneLib.packs['big']!['source.pdf']);
      expect(webLib.rows['big']!['sentence_index'], 12);
      expect(server.puts, greaterThan(3));
      expect(server.bundles.length, lessThanOrEqualTo(2));
      for (final b in server.bundles.values) {
        expect(b.length, lessThan(1024));
      }
    });

    test('a relay that keeps failing ends the run', () async {
      final server = _RelayServer()..failPuts = 1000;
      final web = NearRelayPipe(
        host: true,
        put: server.put,
        take: server.take,
        linger: const Duration(milliseconds: 5),
        idle: const Duration(milliseconds: 5),
      )..start();
      await expectLater(
        NearSync(web, _Mem(), quiet: const Duration(seconds: 30)).run(),
        throwsA(isA<NearSyncError>()),
      );
      web.close();
    });
  });
}


void extrasMain() {
  group('design/410 practice files', () {
    test('voices cross both ways for shared and new papers, and held ones are not resent', () async {
      final (pa, pb) = _pair();
      final phone = _Mem()..add('p1', _paper(100, 1))..add('both', _paper(10, 2));
      phone.extras['p1'] = {'a.bin': _bytes(5000, 1)};
      phone.extras['both'] = {'x.bin': _bytes(300, 2), 'same.bin': _bytes(10, 3)};
      final web = _Mem()..add('both', _paper(10, 2));
      web.extras['both'] = {'y.bin': _bytes(200, 4), 'same.bin': _bytes(10, 9)};
      final results = await Future.wait([
        NearSync(pa, phone).run(),
        NearSync(pb, web).run(),
      ]);
      expect(web.extras['p1']!.keys, ['a.bin']);
      expect(web.extras['both']!.keys.toSet(), {'x.bin', 'y.bin', 'same.bin'});
      expect(web.extras['both']!['same.bin'], _bytes(10, 9));
      expect(phone.extras['both']!.keys.toSet(), {'x.bin', 'y.bin', 'same.bin'});
      expect(phone.extras['both']!['same.bin'], _bytes(10, 3));
      expect(results[1].extrasIn, 2);
      expect(results[0].extrasIn, 1);
      expect(results[0].times.keys, containsAll(['pack_ms', 'send_ms', 'room_ms', 'store_ms', 'sync_ms']));
    });

    test('mergeShadowingTakes fills empty slots and keeps filled ones', () {
      final mine = {
        'version': 1,
        'cache_id': 'c',
        'sentences': {
          's1': {
            'chunks': [
              {'status': 'done', 'blob_key': 'mine1', 'mime': 'audio/m4a'},
              {'status': 'empty', 'blob_key': null, 'mime': null},
            ],
          },
        },
      };
      final theirs = {
        'sentences': {
          's1': {
            'chunks': [
              {'status': 'done', 'blob_key': 'their1', 'mime': 'audio/m4a'},
              {'status': 'done', 'blob_key': 'their2', 'mime': 'audio/m4a'},
              {'status': 'done', 'blob_key': 'their3', 'mime': 'audio/m4a'},
            ],
          },
          's2': {
            'chunks': [
              {'status': 'done', 'blob_key': 'their4', 'mime': 'audio/m4a'},
            ],
          },
        },
      };
      final out = mergeShadowingTakes(mine, theirs, cacheId: 'c');
      final s1 = (out['sentences'] as Map)['s1']['chunks'] as List;
      expect([for (final c in s1) c['blob_key']], ['mine1', 'their2', 'their3']);
      expect(((out['sentences'] as Map)['s2']['chunks'] as List).single['blob_key'], 'their4');
      expect(mergeShadowingTakes(null, theirs, cacheId: 'c')['cache_id'], 'c');
    });

    test('the web keeps shadowing in browser storage and a merge never replaces', () async {
      debugNoLocalDisk = true;
      debugBrowserDisk = MemoryDiskFs();
      addTearDown(() {
        debugBrowserDisk = null;
        debugNoLocalDisk = false;
      });
      final store = ShadowingDiskStore()..bindUid('web');
      expect(await store.uidRoot(), isNull);
      expect(await store.writeVoiceBytes('abcd1234', 'k1', [1, 2, 3]), isTrue);
      expect(
        await store.writeTakesJson('abcd1234', {
          'version': 1,
          'cache_id': 'abcd1234',
          'sentences': {
            's1': {
              'chunks': [
                {'status': 'done', 'blob_key': 'k1', 'mime': 'audio/m4a'},
              ],
            },
          },
        }),
        isTrue,
      );
      expect(await store.listChildDirNames(), ['abcd1234']);
      expect(await store.listVoiceNames('abcd1234'), ['k1.bin']);
      final n = await store.mergePackFiles('abcd1234', {
        'shadowing/voice/k1.bin': Uint8List.fromList([9, 9]),
        'shadowing/voice/k2.bin': Uint8List.fromList([7]),
        'shadowing/voice/../x.bin': Uint8List.fromList([7]),
        'shadowing/chunks.json': Uint8List.fromList(utf8.encode('{"sentences":[]}')),
        'shadowing/takes.json': Uint8List.fromList(utf8.encode(jsonEncode({
          'sentences': {
            's1': {
              'chunks': [
                {'status': 'done', 'blob_key': 'other', 'mime': 'audio/m4a'},
                {'status': 'done', 'blob_key': 'k2', 'mime': 'audio/m4a'},
              ],
            },
          },
        }))),
      });
      expect(n, 3);
      expect(await store.listVoiceNames('abcd1234'), ['k1.bin', 'k2.bin']);
      final pack = await store.listPackFiles('abcd1234');
      expect(pack['shadowing/voice/k1.bin'], [1, 2, 3]);
      final takes = await store.loadTakesJson('abcd1234');
      final chunks = (takes!['sentences'] as Map)['s1']['chunks'] as List;
      expect([for (final c in chunks) c['blob_key']], ['k1', 'k2']);
      final fs = debugBrowserDisk! as MemoryDiskFs;
      expect(fs.files.keys.where((k) => k.endsWith('.part')), isEmpty);
      expect(
        fs.files.keys.every((k) => k.replaceAll(r'\', '/').startsWith('/asr_shadowing/u/web/')),
        isTrue,
      );
    });
  });
}
