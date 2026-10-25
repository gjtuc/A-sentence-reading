// design/451 — near sync over the USB cable, with the PC helper in memory.
import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/services/near_sync.dart';
import 'package:sentence_reading/services/near_usb.dart';
import 'package:sentence_reading/services/near_usb_line.dart';

/// One side of the in-memory helper.
class _Line implements UsbLine {
  final _in = StreamController<Object>();
  _Line? peer;
  final sent = <Uint8List>[];
  var closed = false;

  @override
  Stream<Object> get incoming => _in.stream;

  void control(Map<String, Object?> m) {
    if (!_in.isClosed) _in.add(m);
  }

  @override
  void sendData(Uint8List data) {
    if (closed) throw StateError('closed');
    sent.add(data);
    final copy = Uint8List.fromList(data);
    scheduleMicrotask(() {
      final p = peer;
      if (p != null && !p._in.isClosed) p._in.add(copy);
    });
  }

  @override
  Future<void> close() async {
    closed = true;
    if (!_in.isClosed) await _in.close();
  }
}

class _Mem implements NearLocal {
  final held = <String, NearPaper>{};
  final packs = <String, Map<String, Uint8List>>{};

  void add(String id) {
    held[id] = NearPaper(id: id, title: 'T $id');
    packs[id] = {
      'session.json': Uint8List.fromList(utf8.encode('{"title":"$id"}')),
      'source.pdf': Uint8List.fromList(List<int>.generate(70000, (i) => (i * 7) & 0xff)),
    };
  }

  @override
  Future<List<NearPaper>> papers() async => held.values.toList();

  @override
  Future<Map<String, Uint8List>> pack(String id) async => packs[id] ?? {};

  @override
  Future<bool> store(NearPaper paper, Map<String, Uint8List> files) async {
    held[paper.id] = paper;
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

void main() {
  test('phone frames survive any cut of the TCP stream', () {
    final a = encodeUsbFrame(kUsbKindData, Uint8List.fromList([1, 2, 3]));
    final b = encodeUsbFrame(
      kUsbKindControl,
      Uint8List.fromList(utf8.encode('{"t":"paired"}')),
    );
    final all = Uint8List.fromList([...a, ...b]);
    for (var cut = 0; cut <= all.length; cut++) {
      final r = UsbFrameReader();
      final got = [...r.add(all.sublist(0, cut)), ...r.add(all.sublist(cut))];
      expect(got.length, 2, reason: 'cut $cut');
      expect(got[0], [1, 2, 3]);
      expect(got[1], {'t': 'paired'});
    }
    expect(() => UsbFrameReader().add([0, 0, 0, 0]), throwsFormatException);
  });

  test('no helper or a silent helper means no USB session', () async {
    expect(
      await openNearUsb(connect: ({required Duration timeout}) async => throw StateError('refused')),
      isNull,
    );
    final silent = _Line();
    expect(await openNearUsb(connect: ({required Duration timeout}) async => silent), isNull);
    expect(silent.closed, isTrue);
  });

  test('hello tells about the cable, paired opens the pipe', () async {
    final line = _Line();
    final opening = openNearUsb(connect: ({required Duration timeout}) async => line);
    line.control({'t': 'hello', 'cable': true, 'web': true, 'phone': false});
    final s = (await opening)!;
    expect(s.cable, isTrue);
    expect(s.webThere, isTrue);
    expect(s.isPaired, isFalse);
    line.control({'t': 'paired'});
    await s.paired;
    expect(s.isPaired, isTrue);
    await s.close();
    expect(line.closed, isTrue);
  });

  test('the helper going away ends the wait instead of hanging', () async {
    final line = _Line();
    final s = NearUsbSession(line);
    line.control({'t': 'hello', 'cable': true});
    await s.hello;
    await line.close();
    await expectLater(s.paired, throwsA(isA<NearSyncError>()));
  });

  test('two libraries sync byte for byte through the helper', () async {
    final web = _Line();
    final phone = _Line();
    web.peer = phone;
    phone.peer = web;
    final ws = NearUsbSession(web);
    final ps = NearUsbSession(phone);
    for (final l in [web, phone]) {
      l.control({'t': 'hello', 'cable': true, 'web': true, 'phone': true});
      l.control({'t': 'paired'});
    }
    await Future.wait([ws.paired, ps.paired]);
    final webLib = _Mem()..add('w1');
    final phoneLib = _Mem()
      ..add('p1')
      ..add('p2');
    final r = await Future.wait([
      NearSync(ws.pipe, webLib).run(),
      NearSync(ps.pipe, phoneLib).run(),
    ]);
    expect(r[0].papersIn, 2);
    expect(r[1].papersIn, 1);
    expect(webLib.packs['p2']!['source.pdf'], phoneLib.packs['p2']!['source.pdf']);
    expect(phoneLib.held.keys, unorderedEquals(['p1', 'p2', 'w1']));
  });
}
