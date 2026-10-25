// design/450 — a delete on one device spreads through near sync.
import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/near_gone_store.dart';
import 'package:sentence_reading/services/disk_fs.dart';
import 'package:sentence_reading/services/local_disk.dart';
import 'package:sentence_reading/services/near_sync.dart';
import 'package:sentence_reading/services/paper_disk_store.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _End implements NearPipe {
  _End(this._out);

  final StreamController<Uint8List> _out;
  final _in = StreamController<Uint8List>();

  @override
  Stream<Uint8List> get frames => _in.stream;

  @override
  Future<void> send(Uint8List frame) async {
    if (_out.isClosed || _in.isClosed) throw StateError('closed');
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
  aIn.stream.listen((f) => a._in.add(f));
  bIn.stream.listen((f) => b._in.add(f));
  return (a, b);
}

Map<String, Uint8List> _paper(String id) => {
      'session.json': Uint8List.fromList(utf8.encode('{"title":"$id","sentences":[]}')),
      'source.pdf': Uint8List.fromList(List<int>.generate(300, (i) => i & 0xff)),
    };

/// A device without design/450 (no delete record).
class _Old implements NearLocal {
  final held = <String, NearPaper>{};
  final packs = <String, Map<String, Uint8List>>{};

  void add(String id, {int added = 0}) {
    held[id] = NearPaper(id: id, title: 'T $id', added: added);
    packs[id] = _paper(id);
  }

  @override
  Future<List<NearPaper>> papers() async => held.values.toList();

  @override
  Future<Map<String, Uint8List>> pack(String id) async => packs[id] ?? {};

  @override
  Future<bool> store(NearPaper paper, Map<String, Uint8List> files) async {
    held[paper.id] = NearPaper(id: paper.id, title: paper.title, added: 999999);
    packs[paper.id] = files;
    return true;
  }

  @override
  Future<Map<String, Map<String, dynamic>>> progress() async => {};

  @override
  Future<int> mergeProgress(Map<String, Map<String, dynamic>> rows) async => 0;

  @override
  Future<Map<String, List<String>>> extraNames() async => {};

  @override
  Future<Map<String, Uint8List>> extraPack(String id, Set<String> skipNames) async => {};

  @override
  Future<int> mergeExtra(String id, Map<String, Uint8List> files) async => 0;
}

class _New extends _Old implements NearForget {
  final goneMap = <String, int>{};
  final hiddenSet = <String>{};
  final dropped = <String>[];

  @override
  Future<Map<String, int>> gone() async => Map.of(goneMap);

  @override
  Future<Set<String>> hidden() async => Set.of(hiddenSet);

  @override
  Future<void> forget(Map<String, int> gone, List<String> drop) async {
    goneMap
      ..clear()
      ..addAll(nearGoneMerge(goneMap, gone));
    for (final id in drop) {
      held.remove(id);
      packs.remove(id);
      dropped.add(id);
    }
  }
}

Future<List<NearSyncReport>> _sync(NearLocal a, NearLocal b) {
  final (pa, pb) = _pair();
  return Future.wait([NearSync(pa, a).run(), NearSync(pb, b).run()]);
}

void main() {
  test('a paper deleted on the phone is deleted on the web, not sent back', () async {
    final phone = _New()..goneMap['gone1'] = 5000;
    final web = _New()
      ..add('gone1')
      ..add('kept');
    final r = await _sync(phone, web);
    expect(web.held.keys, ['kept']);
    expect(web.dropped, ['gone1']);
    expect(r[1].papersGone, 1);
    expect(phone.held.keys, ['kept']);
    expect(r[0].papersIn, 1);
    expect(web.goneMap['gone1'], 5000);
  });

  test('a delete on the web reaches the phone the same way', () async {
    final phone = _New()..add('x', added: 100);
    final web = _New()..goneMap['x'] = 200;
    final r = await _sync(phone, web);
    expect(phone.held, isEmpty);
    expect(r[0].papersGone, 1);
    expect(web.held, isEmpty);
  });

  test('importing again after the delete spreads the paper again', () async {
    final phone = _New()..goneMap['p'] = 5000;
    final web = _New()..add('p', added: 9000);
    final r = await _sync(phone, web);
    expect(web.held.keys, ['p']);
    expect(web.dropped, isEmpty);
    expect(phone.held.keys, ['p']);
    expect(r[0].papersIn, 1);
  });

  test('a paper deleted here and imported again there replaces the old copy', () async {
    final phone = _New()
      ..add('p', added: 1000)
      ..goneMap['q'] = 1;
    final web = _New()
      ..add('p', added: 8000)
      ..goneMap['p'] = 5000;
    await _sync(phone, web);
    expect(phone.dropped, ['p']);
    expect(phone.held.keys, ['p']);
    expect(web.held.keys, ['p']);
  });

  test('a hidden paper that can still be undone is neither sent nor taken', () async {
    final phone = _New()
      ..add('h')
      ..hiddenSet.add('h');
    final web = _New()..add('w');
    final r = await _sync(phone, web);
    expect(web.held.keys, ['w']);
    expect(r[1].papersIn, 0);
    expect(phone.held.keys, unorderedEquals(['h', 'w']));
    expect(phone.dropped, isEmpty);
  });

  test('an older device without the delete record cannot bring a paper back', () async {
    final phone = _New()..goneMap['a'] = 5000;
    final old = _Old()
      ..add('a')
      ..add('b');
    final r = await _sync(phone, old);
    expect(phone.held.keys, ['b']);
    expect(r[0].papersIn, 1);
    expect(old.held.keys, unorderedEquals(['a', 'b']));
  });

  test('the delete record keeps the newest time and a bounded size', () {
    final m = nearGoneMerge({'a': 5, 'b': 9}, {'a': 7, 'b': 3, '': 4, 'c': 0});
    expect(m, {'a': 7, 'b': 9});
    final big = {for (var i = 0; i < kNearGoneKeep + 5; i++) 'id$i': i + 1};
    final kept = nearGoneMerge({}, big);
    expect(kept.length, kNearGoneKeep);
    expect(kept.containsKey('id0'), isFalse);
    expect(kept.containsKey('id${kNearGoneKeep + 4}'), isTrue);
    expect(nearGoneDecode('{"a":3}'), {'a': 3});
    expect(nearGoneDecode('not json'), isEmpty);
  });

  test('the delete record is kept per account', () async {
    SharedPreferences.setMockInitialValues({});
    await addNearGone('u1', {'a': 10});
    await addNearGone('u1', {'a': 4, 'b': 6});
    expect(await loadNearGone('u1'), {'a': 10, 'b': 6});
    expect(await loadNearGone('u2'), isEmpty);
    await addNearGone(null, {'z': 1});
    expect(await loadNearGone(''), isEmpty);
  });

  test('the paper index stamps the first arrival and keeps it on updates', () async {
    SharedPreferences.setMockInitialValues({});
    debugNoLocalDisk = true;
    debugBrowserDisk = MemoryDiskFs();
    addTearDown(() {
      debugBrowserDisk = null;
      debugNoLocalDisk = false;
    });
    final disk = PaperDiskStore()..bindUid('u');
    final before = DateTime.now().millisecondsSinceEpoch;
    await disk.upsertIndex(PaperDiskIndexEntry(id: 'p1', title: 'One'), caller: 'test');
    final first = (await disk.listIndex()).single;
    expect(first.addedMs, greaterThanOrEqualTo(before - 1000));
    await Future<void>.delayed(const Duration(milliseconds: 5));
    await disk.upsertIndex(
      PaperDiskIndexEntry(id: 'p1', title: 'One again', pairedCacheId: 'p2'),
      caller: 'test',
    );
    final again = (await disk.listIndex()).single;
    expect(again.title, 'One again');
    expect(again.addedAt, first.addedAt);
    final legacy = PaperDiskIndexEntry.fromJson({'id': 'old', 'title': 'Old'});
    expect(legacy.addedMs, 0);
    expect(legacy.toJson().containsKey('added_at'), isFalse);
  });
}
