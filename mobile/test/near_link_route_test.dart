// design/454 — which way near sync goes when the USB helper and the server both exist.
import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/client.dart';
import 'package:sentence_reading/services/near_link.dart';
import 'package:sentence_reading/services/near_sync.dart';
import 'package:sentence_reading/services/near_usb.dart';
import 'package:sentence_reading/services/near_usb_line.dart';
import 'package:sentence_reading/widgets/near_sync_sheet.dart';

class _Line implements UsbLine {
  final _in = StreamController<Object>();
  _Line? peer;
  var closed = false;

  @override
  Stream<Object> get incoming => _in.stream;

  void control(Map<String, Object?> m) {
    if (!_in.isClosed) _in.add(m);
  }

  @override
  void sendData(Uint8List data) {
    if (closed) throw StateError('closed');
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

class _Client extends AsrClient {
  _Client({this.linkOnClaim = -1});

  /// The claim number (1-based) that finds the web's link; -1 = never.
  final int linkOnClaim;
  var claims = 0;
  var creates = 0;

  @override
  Future<({String linkId, Map<String, dynamic> offer})?> nearClaimLink() async {
    claims += 1;
    if (claims == linkOnClaim) {
      return (linkId: 'L1', offer: <String, dynamic>{'type': 'offer', 'sdp': 'v=0'});
    }
    return null;
  }

  @override
  Future<String> nearCreateLink(Map<String, Object?> offer) async {
    creates += 1;
    return 'L1';
  }

  @override
  Future<Map<String, dynamic>?> nearPeekAnswer(String linkId) async => null;

  @override
  Future<void> nearDropLink(String linkId) async {}
}

class _Mem implements NearLocal {
  _Mem(List<String> ids) {
    for (final id in ids) {
      held[id] = NearPaper(id: id, title: 'T $id');
      packs[id] = {
        'session.json': Uint8List.fromList(utf8.encode('{"title":"$id"}')),
        'source.pdf': Uint8List.fromList(List<int>.generate(5000, (i) => i & 0xff)),
      };
    }
  }

  final held = <String, NearPaper>{};
  final packs = <String, Map<String, Uint8List>>{};

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

/// Our side's session (hello already in) and the other side's line.
Future<(NearUsbSession, _Line, _Line)> _helper(Map<String, Object?> hello) async {
  final mine = _Line();
  final theirs = _Line();
  mine.peer = theirs;
  theirs.peer = mine;
  final s = NearUsbSession(mine);
  mine.control({'t': 'hello', ...hello});
  await s.hello;
  return (s, mine, theirs);
}

/// Pair both lines and run the other side's sync.
Future<NearSyncReport> _otherSide(_Line mine, _Line theirs, NearLocal lib) async {
  final s = NearUsbSession(theirs);
  theirs.control({'t': 'hello', 'cable': true});
  mine.control({'t': 'paired'});
  theirs.control({'t': 'paired'});
  await s.paired;
  return NearSync(s.pipe, lib).run();
}

Future<void> _until(bool Function() ok) async {
  for (var i = 0; i < 200 && !ok(); i++) {
    await Future<void>.delayed(const Duration(milliseconds: 50));
  }
  expect(ok(), isTrue);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('a phone that pressed first waits at the helper and meets the web there', () async {
    final (usb, mine, theirs) = await _helper({'cable': true, 'web': false, 'phone': true});
    final client = _Client();
    final link = NearLink(client: client, local: _Mem(['p1']), usbOpen: () async => usb);
    final run = link.join();
    await _until(() => link.step == NearStep.waiting && client.claims >= 1);
    expect(link.via, 'usb');
    final other = await _otherSide(mine, theirs, _Mem(['w1']));
    await run;
    expect(link.step, NearStep.done);
    expect(link.via, 'usb');
    expect(link.report!.papersIn, 1);
    expect(other.papersIn, 1);
  }, timeout: const Timeout(Duration(seconds: 30)));

  test('a phone waiting at the helper takes the server link of a web that is not there', () async {
    final (usb, mine, _) = await _helper({'cable': true, 'web': false, 'phone': true});
    final client = _Client(linkOnClaim: 2);
    final link = NearLink(client: client, local: _Mem(['p1']), usbOpen: () async => usb);
    await link.join();
    expect(client.claims, 2);
    expect(mine.closed, isTrue);
    expect(link.via, isNot('usb'));
  }, timeout: const Timeout(Duration(seconds: 30)));

  test('a web finding the phone already at the helper makes no server link', () async {
    final (usb, mine, theirs) = await _helper({'cable': true, 'web': true, 'phone': true});
    final client = _Client();
    final link = NearLink(client: client, local: _Mem(['w1']), usbOpen: () async => usb);
    final run = link.host();
    await _otherSide(mine, theirs, _Mem(['p1']));
    await run;
    expect(link.step, NearStep.done);
    expect(link.via, 'usb');
    expect(client.creates, 0);
  }, timeout: const Timeout(Duration(seconds: 30)));

  test('a web whose server side fails still waits for the phone at the helper', () async {
    final (usb, mine, theirs) = await _helper({'cable': true, 'web': true, 'phone': false});
    final client = _Client();
    final link = NearLink(client: client, local: _Mem(['w1']), usbOpen: () async => usb);
    final run = link.host();
    await _until(() => link.step == NearStep.waiting);
    await _otherSide(mine, theirs, _Mem(['p1']));
    await run;
    expect(link.step, NearStep.done);
    expect(link.via, 'usb');
    expect(link.report!.papersIn, 1);
  }, timeout: const Timeout(Duration(seconds: 30)));

  test('no cable at the helper: the web goes the server way only', () async {
    final (usb, mine, _) = await _helper({'cable': false, 'web': true, 'phone': false});
    final client = _Client();
    final link = NearLink(client: client, local: _Mem(['w1']), usbOpen: () async => usb);
    await link.host();
    expect(mine.closed, isTrue);
    expect(link.via, isNot('usb'));
  }, timeout: const Timeout(Duration(seconds: 30)));

  test('a later server version is told apart from the page version', () {
    expect(nearVersionNewer('0.3.474', '0.3.472'), isTrue);
    expect(nearVersionNewer('0.3.1000', '0.3.999'), isTrue);
    expect(nearVersionNewer('0.3.472', '0.3.472'), isFalse);
    expect(nearVersionNewer('0.3.471', '0.3.472'), isFalse);
    expect(nearVersionNewer('', '0.3.472'), isFalse);
  });
}
