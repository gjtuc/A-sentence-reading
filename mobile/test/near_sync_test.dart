// design/410 — phone <-> web near sync protocol, in memory.
import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/progress_store.dart';
import 'package:sentence_reading/services/disk_fs.dart';
import 'package:sentence_reading/services/local_disk.dart';
import 'package:sentence_reading/services/near_library_local.dart';
import 'package:sentence_reading/services/near_sync.dart';
import 'package:sentence_reading/services/paper_disk_store.dart';
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
}
