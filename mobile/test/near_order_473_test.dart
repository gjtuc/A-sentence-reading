// design/473 — near sync settles one library order on both devices.
import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/library_order_models.dart';
import 'package:sentence_reading/services/near_sync.dart';

class _End implements NearPipe {
  _End(this._out);

  final StreamController<Uint8List> _out;
  final _in = StreamController<Uint8List>();

  @override
  Stream<Uint8List> get frames => _in.stream;

  @override
  Future<void> send(Uint8List frame) async {
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

class _Dev implements NearLocal, NearOrdering {
  _Dev(List<String> ids, {required this.at, this.ordering = true})
      : shown = List.of(ids),
        held = {for (final id in ids) id};

  List<String> shown;
  int at;
  final Set<String> held;
  final bool ordering;
  final taken = <NearOrder>[];

  @override
  Future<List<NearPaper>> papers() async =>
      [for (final id in held) NearPaper(id: id, title: 'T $id')];

  @override
  Future<Map<String, Uint8List>> pack(String id) async =>
      {'session.json': Uint8List.fromList([1, 2, 3])};

  @override
  Future<bool> store(NearPaper paper, Map<String, Uint8List> files) async {
    held.add(paper.id);
    return true;
  }

  @override
  Future<Map<String, Map<String, dynamic>>> progress() async => {};

  @override
  Future<int> mergeProgress(Map<String, Map<String, dynamic>> rows) async => 0;

  @override
  Future<Map<String, List<String>>> extraNames() async => {};

  @override
  Future<Map<String, Uint8List>> extraPack(String id, Set<String> skip) async => {};

  @override
  Future<int> mergeExtra(String id, Map<String, Uint8List> files) async => 0;

  @override
  Future<NearOrder> order() async {
    if (!ordering) throw StateError('old device');
    return NearOrder(ids: shown, at: at);
  }

  @override
  Future<void> takeOrder(NearOrder order) async {
    taken.add(order);
    shown = order.ids;
    at = order.at;
  }
}

Future<(NearSyncReport, NearSyncReport)> _sync(_Dev a, _Dev b) async {
  final (pa, pb) = _pair();
  final r = await Future.wait([NearSync(pa, a).run(), NearSync(pb, b).run()]);
  return (r[0], r[1]);
}

void main() {
  test('design/473 the later order wins; the loser papers keep their neighbours', () {
    expect(
      mergeLibraryOrder(winner: ['a', 'b', 'c'], loser: ['x', 'a', 'y', 'c', 'z']),
      ['x', 'a', 'y', 'b', 'c', 'z'],
    );
    expect(mergeLibraryOrder(winner: ['a'], loser: ['p', 'q', 'a']), ['p', 'q', 'a']);
  });

  test('design/473 the saved order keeps when it was dragged', () {
    final raw = serializeLibraryOrderPref(['a', 'b'], at: 1234);
    expect(parseLibraryOrderPref(raw), ['a', 'b']);
    expect(parseLibraryOrderAt(raw), 1234);
    expect(parseLibraryOrderAt(serializeLibraryOrderPref(['a'])), 0);
    expect(parseLibraryOrderAt(null), -1);
  });

  test('design/473 both sides compute the same order; a tie changes nothing', () {
    const phone = NearOrder(ids: ['a', 'b', 'c'], at: 100);
    const web = NearOrder(ids: ['c', 'b'], at: 200);
    final onPhone = nearMergedOrder(phone, web)!;
    final onWeb = nearMergedOrder(web, phone)!;
    expect(onPhone.ids, ['a', 'c', 'b']);
    expect(onWeb.ids, onPhone.ids);
    expect(onPhone.at, 200);
    expect(onWeb.at, 200);
    expect(nearMergedOrder(phone, const NearOrder(ids: ['c', 'a'], at: 100)), isNull);
    expect(nearMergedOrder(phone, const NearOrder(ids: ['b', 'a'], at: 50)), isNull);
    expect(nearMergedOrder(const NearOrder(ids: ['a'], at: -1), const NearOrder(ids: ['b', 'a'], at: 0))!.ids,
        ['b', 'a']);
  });

  test('design/473 a sync leaves both devices in the order dragged last', () async {
    final phone = _Dev(['a', 'b', 'c'], at: 100);
    final web = _Dev(['c', 'b'], at: 200);
    final (rp, rw) = await _sync(phone, web);
    expect(phone.shown, ['a', 'c', 'b']);
    expect(web.shown, ['a', 'c', 'b']);
    expect(web.held, containsAll(['a', 'b', 'c']));
    expect(rp.orderTaken, isTrue);
    expect(rw.orderTaken, isTrue);
  });

  test('design/473 the same order twice is left alone', () async {
    final phone = _Dev(['a', 'b'], at: 300);
    final web = _Dev(['a', 'b'], at: 300);
    final (rp, rw) = await _sync(phone, web);
    expect(phone.taken, isEmpty);
    expect(web.taken, isEmpty);
    expect(rp.orderTaken || rw.orderTaken, isFalse);
  });
}
