import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/state/read_done.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _FakeTransport implements ReadDoneTransport {
  Map<String, Map<String, dynamic>> remote = {};
  final List<String> puts = [];
  bool fail = false;

  @override
  Future<Map<String, Map<String, dynamic>>> all() async {
    if (fail) throw StateError('offline');
    return remote;
  }

  @override
  Future<void> put(String cacheId, Map<String, Object?> mark) async {
    if (fail) throw StateError('offline');
    puts.add(cacheId);
    remote[cacheId] = Map<String, dynamic>.from(mark);
  }
}

final _h = 'a' * 64;

ReadDoneStore _store(_FakeTransport t, DateTime now) => ReadDoneStore(
      transport: t,
      deviceId: () async => 'dev-1',
      clock: () => now,
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('a mark is shown at once, sent, and keeps the PDF hash', () async {
    final t = _FakeTransport();
    final s = _store(t, DateTime.utc(2026, 10, 22, 9));
    await s.bindUid('u1');
    await s.mark('c1', done: true, hash: _h.toUpperCase());
    expect(s.isDone('c1'), isTrue);
    expect(s.doneHashes, {_h});
    expect(t.puts, ['c1']);
    expect(t.remote['c1']!['h'], _h);
  });

  test('a newer mark from the server wins, an older one does not', () async {
    final t = _FakeTransport();
    final s = _store(t, DateTime.utc(2026, 10, 22, 9));
    await s.bindUid('u1');
    await s.mark('c1', done: true);
    t.remote['c1'] = {
      'done': false,
      'at': '2026-10-22T10:00:00Z',
      'dev': 'web',
    };
    t.remote['c2'] = {
      'done': true,
      'at': '2026-10-22T08:00:00Z',
      'dev': 'web',
    };
    await s.pull();
    expect(s.isDone('c1'), isFalse);
    expect(s.isDone('c2'), isTrue);

    t.remote['c1'] = {
      'done': true,
      'at': '2026-10-22T07:00:00Z',
      'dev': 'web',
    };
    await s.pull();
    expect(s.isDone('c1'), isFalse);
  });

  test('a mark made offline is kept and sent on the next pull', () async {
    final t = _FakeTransport()..fail = true;
    final s = _store(t, DateTime.utc(2026, 10, 22, 9));
    await s.bindUid('u1');
    await s.mark('c1', done: true);
    expect(s.isDone('c1'), isTrue);
    expect(t.puts, isEmpty);

    t.fail = false;
    await s.pull();
    expect(t.puts, ['c1']);
    expect(t.remote['c1']!['done'], isTrue);
  });

  test('marks come back from the device after a restart, per account',
      () async {
    final t = _FakeTransport()..fail = true;
    final a = _store(t, DateTime.utc(2026, 10, 22, 9));
    await a.bindUid('u1');
    await a.mark('c1', done: true, hash: _h);

    final b = _store(t, DateTime.utc(2026, 10, 22, 9));
    await b.bindUid('u1');
    expect(b.isDone('c1'), isTrue);
    expect(b.doneHashes, {_h});

    final other = _store(t, DateTime.utc(2026, 10, 22, 9));
    await other.bindUid('u2');
    expect(other.isDone('c1'), isFalse);

    final p = await SharedPreferences.getInstance();
    final saved = jsonDecode(p.getString(ReadDoneStore.prefsKey('u1'))!);
    expect((saved['unsent'] as List).contains('c1'), isTrue);
  });

  test('un-marking drops the hash from the import list', () async {
    final t = _FakeTransport();
    final s = _store(t, DateTime.utc(2026, 10, 22, 9));
    await s.bindUid('u1');
    await s.mark('c1', done: true, hash: _h);
    await s.mark('c1', done: false);
    expect(s.isDone('c1'), isFalse);
    expect(s.doneHashes, isEmpty);
  });
}
