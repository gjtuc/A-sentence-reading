// design/411 - live reading spots between the devices of one account.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/progress_store.dart';
import 'package:sentence_reading/services/spot_sync.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _Server implements SpotTransport {
  int rev = 0;
  final rows = <String, Map<String, dynamic>>{};
  var fail = false;
  final puts = <String>[];

  @override
  Future<void> put(String cacheId, Map<String, Object?> spot) async {
    if (fail) throw StateError('down');
    puts.add(cacheId);
    final held = rows[cacheId];
    if (held != null && '${held['at']}'.compareTo('${spot['at']}') >= 0) return;
    rev += 1;
    rows[cacheId] = {...spot, 'rev': rev};
  }

  @override
  Future<SpotPage> since(int after) async {
    if (fail) throw StateError('down');
    return (
      rev: rev,
      spots: {
        for (final e in rows.entries)
          if ((e.value['rev'] as int) > after) e.key: Map<String, dynamic>.from(e.value),
      },
    );
  }
}

void main() {
  test('a move on one device reaches the other, never its own', () async {
    final server = _Server();
    var t = DateTime.utc(2026, 10, 17, 10);
    final gotPhone = <String>[];
    final gotWeb = <String>[];
    final phone = SpotSync(
      transport: server,
      deviceId: 'phone0001',
      debounce: Duration.zero,
      clock: () => t,
      onRemote: (cid, si, fi, at) async => gotPhone.add('$cid:$si:$fi'),
    );
    final web = SpotSync(
      transport: server,
      deviceId: 'web000001',
      debounce: Duration.zero,
      clock: () => t,
      onRemote: (cid, si, fi, at) async => gotWeb.add('$cid:$si:$fi:$at'),
    );
    phone.noteLocal('p1', 3, 0);
    phone.noteLocal('p1', 4, 1);
    await phone.flush();
    expect(server.puts, ['p1']);
    expect(await phone.poll(), 0);
    expect(await web.poll(), 1);
    expect(gotWeb, ['p1:4:1:2026-10-17T10:00:00.000Z']);
    expect(await web.poll(), 0, reason: 'nothing new since the last rev');
    t = t.add(const Duration(seconds: 5));
    phone.noteLocal('p1', 5, 1);
    await phone.flush();
    expect(await web.poll(), 1);
    expect(gotWeb.last, startsWith('p1:5:1'));
    expect(gotPhone, isEmpty);
    phone.close();
    web.close();
  });

  test('a move not sent yet is not overwritten by an older spot', () async {
    final server = _Server();
    final got = <String>[];
    final other = SpotSync(transport: server, deviceId: 'other0001', debounce: Duration.zero, onRemote: (a, b, c, d) async {});
    other.noteLocal('p1', 9, 0);
    await other.flush();
    final me = SpotSync(
      transport: server,
      deviceId: 'me0000001',
      debounce: const Duration(hours: 1),
      onRemote: (cid, si, fi, at) async => got.add(cid),
    );
    me.noteLocal('p1', 2, 0);
    expect(await me.poll(), 0);
    expect(got, isEmpty);
    me.close();
    other.close();
  });

  test('failures slow the poll and a failed put is kept for the next flush', () async {
    final server = _Server()..fail = true;
    final errors = <String>[];
    final s = SpotSync(
      transport: server,
      deviceId: 'phone0001',
      debounce: Duration.zero,
      onRemote: (a, b, c, d) async {},
      onFailure: (stage, _) => errors.add(stage),
    );
    s.noteLocal('p1', 1, 0);
    await s.flush();
    await s.poll();
    await s.poll();
    expect(s.slow, isTrue);
    expect(errors, ['put'], reason: 'reported once per streak');
    server.fail = false;
    await s.flush();
    expect(server.rows.keys, ['p1']);
    expect(s.failures, 0);
    s.close();
  });

  test('saving the same spot keeps the time it was reached; a taken spot keeps its time', () async {
    SharedPreferences.setMockInitialValues({});
    await saveProgressRow(uid: 'u1', cacheId: 'c1', sentenceIndex: 3, figureIndex: 0, at: '2026-10-17T10:00:00.000Z');
    await saveProgressRow(uid: 'u1', cacheId: 'c1', sentenceIndex: 3, figureIndex: 0);
    expect(await loadProgressAt(uid: 'u1', cacheId: 'c1'), '2026-10-17T10:00:00.000Z');
    await saveProgressRow(uid: 'u1', cacheId: 'c1', sentenceIndex: 4, figureIndex: 0);
    expect((await loadProgressAt(uid: 'u1', cacheId: 'c1')).compareTo('2026-10-17T10:00:00.000Z'), greaterThan(0));
  });

  test('remote spots are kept apart, newest only, per account', () async {
    SharedPreferences.setMockInitialValues({});
    expect(await saveRemoteSpot(uid: 'u1', cacheId: 'c1', spot: (si: 5, fi: 1, at: '2026-10-17T10:00:05Z')), isTrue);
    expect(await saveRemoteSpot(uid: 'u1', cacheId: 'c1', spot: (si: 2, fi: 0, at: '2026-10-17T10:00:01Z')), isFalse);
    expect(await loadRemoteSpot(uid: 'u1', cacheId: 'c1'), (si: 5, fi: 1, at: '2026-10-17T10:00:05Z'));
    expect(await loadRemoteSpot(uid: 'u2', cacheId: 'c1'), isNull);
    expect(await loadProgressAt(uid: 'u1', cacheId: 'c1'), '', reason: 'own rows untouched');
  });

  test('all remote spots of an account load at once for the library labels', () async {
    SharedPreferences.setMockInitialValues({});
    await saveRemoteSpot(uid: 'u1', cacheId: 'c1', spot: (si: 5, fi: 1, at: '2026-10-17T10:00:05Z'));
    await saveRemoteSpot(uid: 'u1', cacheId: 'c2', spot: (si: 9, fi: 0, at: '2026-10-17T10:00:07Z'));
    await saveRemoteSpot(uid: 'u2', cacheId: 'c3', spot: (si: 1, fi: 0, at: '2026-10-17T10:00:09Z'));
    final all = await loadRemoteSpots(uid: 'u1');
    expect(all.keys.toSet(), {'c1', 'c2'});
    expect(all['c2'], (si: 9, fi: 0, at: '2026-10-17T10:00:07Z'));
    expect(await loadRemoteSpots(uid: 'u9'), isEmpty);
  });

  test('design/509 practice cursor keys ride the spot store', () {
    expect(practiceSpotKey(' 7d506b60fb6b '), 'p.7d506b60fb6b');
    expect(practiceSpotKey('abc#r3'), isNull);
    expect(practiceSpotKey(''), isNull);
    expect(practiceSpotKey('x' * 95), isNull);
    expect(practiceSpotCacheId('p.7d506b60fb6b'), '7d506b60fb6b');
    expect(practiceSpotCacheId('7d506b60fb6b'), isNull);
    expect(practiceSpotCacheId('p.'), isNull);
  });

  test('design/509 library publishes and follows practice cursors', () {
    final lib = File('lib/state/library_controller.dart').readAsStringSync();
    final record = lib.split('Future<void> recordPracticeProgress(')[1].split('Future<void> _onRemotePracticeSpot(')[0];
    expect(record.contains('_spotSync?.noteLocal(key, sentenceIndex, chunkIndex)'), isTrue);
    final remote = lib.split('Future<void> _onRemoteSpot(')[1].split('final uid = _spotUid;')[0];
    expect(remote.contains('practiceSpotCacheId(cacheId)'), isTrue);
    expect(remote.contains('_onRemotePracticeSpot('), isTrue);
  });

  test('design/509 opening the calendar pulls the other devices first', () {
    final screen =
        File('lib/screens/shadowing_practice_screen.dart').readAsStringSync();
    final open = screen.split('void _openFocusCalendar()')[1].split('showFocusPracticeCalendarSheet(')[0];
    expect(open.contains('_focus.refreshFromCloud()'), isTrue);
  });

  test('design/511 polling stops after a quiet spell and comes back on input', () {
    expect(kSpotIdleStop, const Duration(minutes: 5));
    final lib = File('lib/state/library_controller.dart').readAsStringSync();
    final arm = lib.split('void _armSpotPoll(Duration wait)')[1].split('Future<void> _onRemoteSpot(')[0];
    expect(arm.contains('DateTime.now().difference(_spotActiveAt) >= kSpotIdleStop'), isTrue);
    expect(arm.contains('_spotIdle = true;'), isTrue);
    final note = lib.split('void noteSpotActivity()')[1].split('void _onSpotPointer(')[0];
    expect(note.contains('_armSpotPoll(Duration.zero)'), isTrue);
    expect(lib.contains('pointerRouter.addGlobalRoute(_onSpotPointer)'), isTrue);
    expect(lib.contains('HardwareKeyboard.instance.addHandler(_onSpotKey)'), isTrue);
    final open = lib.split('Future<void> persistOpenedProgress(')[1].split('// A spot that came from')[0];
    expect(open.contains('noteSpotActivity();'), isTrue);
    expect(lib.contains('AppLifecycleListener(onResume: noteSpotActivity)'), isTrue);
    final pointer = lib.split('void _onSpotPointer(PointerEvent e)')[1].split('bool _onSpotKey(')[0];
    expect(pointer.contains('PointerHoverEvent'), isFalse);
    expect(pointer.contains('_spotFocused'), isTrue);
    final key = lib.split('bool _onSpotKey(KeyEvent e)')[1].split('void _hookSpotInput()')[0];
    expect(key.contains('if (_spotFocused) noteSpotActivity();'), isTrue);
  });
}
