import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/services/cable_auto_sync.dart';
import 'package:sentence_reading/services/helper_store.dart';

void main() {
  test('phone syncs once per plug-in and again after the cable comes back', () async {
    Map<String, Object?>? answer;
    var starts = 0;
    var now = DateTime(2026, 10, 31, 12);
    final w = PhoneCableWatcher(
      probe: () async => answer,
      start: () async => starts++,
      now: () => now,
    );
    await w.tick();
    expect(starts, 0);

    answer = {'t': 'hello', 'watch': false};
    await w.tick();
    expect(starts, 0, reason: 'no web page is open');

    answer = {'t': 'hello', 'watch': true};
    await w.tick();
    await w.tick();
    expect(starts, 1, reason: 'once per plug-in');

    answer = null;
    await w.tick();
    answer = {'t': 'hello', 'watch': true};
    await w.tick();
    expect(starts, 1, reason: 'one missed probe is not a pulled cable');

    answer = null;
    await w.tick();
    await w.tick();
    answer = {'t': 'hello', 'watch': true};
    await w.tick();
    expect(starts, 2, reason: 'plugged in again');

    now = now.add(const Duration(minutes: 6));
    w.resume();
    await Future<void>.delayed(Duration.zero);
    await w.tick();
    w.pause();
    expect(starts, 3, reason: 'back to the app after a while');
    expect(w.running, isFalse);
  });

  test('web starts a sync when the helper says the phone is there', () async {
    final opened = <StreamController<Map<String, Object?>>>[];
    var hello = <String, Object?>{'t': 'hello', 'watch': true, 'phone': false};
    var fail = 1;
    var starts = 0;
    final w = WebCableWatcher(
      open: () async {
        if (fail > 0) {
          fail--;
          return null;
        }
        final c = StreamController<Map<String, Object?>>();
        opened.add(c);
        return HelperWatch(hello: hello, messages: c.stream, close: () async => c.close());
      },
      start: () async {
        starts++;
        await Future<void>.delayed(const Duration(milliseconds: 30));
      },
      firstRetry: const Duration(milliseconds: 20),
      maxRetry: const Duration(milliseconds: 40),
    );
    w.begin();
    await Future<void>.delayed(const Duration(milliseconds: 80));
    expect(opened, hasLength(1), reason: 'retried after the helper was not there');
    expect(w.connected, isTrue);

    opened.single.add({'t': 'phone'});
    opened.single.add({'t': 'phone'});
    await Future<void>.delayed(Duration.zero);
    expect(starts, 1, reason: 'one sync at a time');
    await Future<void>.delayed(const Duration(milliseconds: 50));

    hello = {'t': 'hello', 'watch': true, 'phone': true};
    await opened.single.close();
    await Future<void>.delayed(const Duration(milliseconds: 80));
    expect(opened, hasLength(2), reason: 'reconnected after the helper went away');
    expect(starts, 2, reason: 'the phone was already waiting');

    await w.stop();
    expect(w.connected, isFalse);
  });

  test('old helpers are told to update', () {
    expect(helperIsOld({'helper': '1'}), isTrue);
    expect(helperIsOld({'helper': '2'}), isFalse);
    expect(helperIsOld(null), isFalse);
  });

  test('controller and screens are wired for the cable sync', () {
    final c = File('lib/state/library_controller.dart').readAsStringSync();
    expect(c, contains('WebCableWatcher(open: connectHelperWatch, start: _autoNearSync)'));
    expect(c, contains('PhoneCableWatcher(probe: probeHelperFromPhone, start: _autoNearSync)'));
    expect(c, contains('if (nearSheetOpen || nearAutoBusy) return;'));
    final sheet = File('lib/widgets/near_sync_sheet.dart').readAsStringSync();
    expect(sheet, contains('library.makeNearLink()'));
    expect(sheet, contains('library.nearSheetOpen = true;'));
    final screen = File('lib/screens/library_screen.dart').readAsStringSync();
    expect(screen, contains('nearAutoNote.addListener(_onNearAutoNote)'));
    final tile = File('lib/widgets/helper_settings_tile.dart').readAsStringSync();
    expect(tile, contains('의심스러운 파일 차단됨'));
    expect(tile, contains('⑥'));
    expect(tile, contains('kHelperAutoSync'));
  });
}
