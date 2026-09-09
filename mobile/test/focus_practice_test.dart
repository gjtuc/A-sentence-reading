import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/focus_practice_models.dart';
import 'package:sentence_reading/api/focus_practice_store.dart';
import 'package:sentence_reading/state/focus_practice_controller.dart';

class _MemFocusStore implements FocusPracticeStore {
  final Map<String, String> _data = {};

  @override
  Future<String?> readRaw(String? uid) async =>
      _data[focusPracticePrefsKey(uid)];

  @override
  Future<void> writeRaw(String? uid, String raw) async {
    _data[focusPracticePrefsKey(uid)] = raw;
  }
}

void main() {
  test('day key and prefs key', () {
    expect(
      focusPracticeDayKey(DateTime(2026, 9, 7, 3, 0)),
      '2026-09-07',
    );
    expect(focusPracticePrefsKey(null), kFocusPracticePrefsKeyBase);
    expect(focusPracticePrefsKey('u1'), 'asr.focus_practice.v1.u1');
    expect(formatFocusClock(const Duration(minutes: 9, seconds: 5)), '09:05');
    expect(formatFocusClock(const Duration(hours: 1, minutes: 2, seconds: 3)),
        '01:02:03');
  });

  test('parse v1 migrates into history; other day still readable', () {
    final raw = serializeFocusPracticeDayState(
      const FocusPracticeDayState(
        day: '2020-01-01',
        success: true,
        blocksCompleted: 3,
      ),
    );
    final hist = parseFocusPracticeHistory(raw);
    expect(hist.blocksFor('2020-01-01'), 3);
    final today = parseFocusPracticeDayState(raw);
    expect(today.day, focusPracticeDayKey());
    expect(today.blocksCompleted, 0);
  });

  test('speak segments fill 10m block and stack next', () async {
    var now = DateTime(2026, 9, 7, 10, 0, 0);
    final store = _MemFocusStore();
    final c = FocusPracticeController(
      store: store,
      blockDuration: const Duration(seconds: 10),
      clock: () => now,
    );
    await c.bindUid('u1');
    c.startSession();

    c.beginSpeak();
    now = now.add(const Duration(seconds: 6));
    c.endSpeak();
    expect(c.daySuccess, isFalse);
    expect(c.blocksCompletedToday, 0);
    expect(c.elapsedInBlock, const Duration(seconds: 6));

    c.beginSpeak();
    now = now.add(const Duration(seconds: 5));
    c.endSpeak();
    // 6+5 → first 10s block done, 1s into next
    expect(c.daySuccess, isTrue);
    expect(c.blocksCompletedToday, 1);
    expect(c.elapsedInBlock, const Duration(seconds: 1));

    c.beginSpeak();
    now = now.add(const Duration(seconds: 9));
    c.endSpeak();
    expect(c.blocksCompletedToday, 2);
    expect(c.elapsedInBlock, Duration.zero);

    await c.bindUid('u1');
    expect(c.daySuccess, isTrue);
    expect(c.blocksCompletedToday, 2);
    expect(c.history.blocksFor('2026-09-07'), 2);
  });

  test('pause freezes clock; listen-only does not count', () async {
    var now = DateTime(2026, 9, 7, 12, 0, 0);
    final c = FocusPracticeController(
      store: _MemFocusStore(),
      blockDuration: const Duration(minutes: 10),
      clock: () => now,
    );
    await c.bindUid('u2');
    c.startSession();
    // TTS listen — no beginSpeak
    now = now.add(const Duration(minutes: 3));
    expect(c.displayElapsed, Duration.zero);

    c.beginSpeak();
    now = now.add(const Duration(seconds: 30));
    expect(c.displayElapsed, const Duration(seconds: 30));
    c.pause();
    now = now.add(const Duration(minutes: 5));
    expect(c.speaking, isFalse);
    expect(c.elapsedInBlock, const Duration(seconds: 30));
    expect(c.displayElapsed, const Duration(seconds: 30));
  });

  test('give up keeps day success but resets unfinished block', () async {
    var now = DateTime(2026, 9, 7, 14, 0, 0);
    final c = FocusPracticeController(
      store: _MemFocusStore(),
      blockDuration: const Duration(seconds: 10),
      clock: () => now,
    );
    await c.bindUid('u3');
    c.startSession();
    c.beginSpeak();
    now = now.add(const Duration(seconds: 10));
    c.endSpeak();
    expect(c.daySuccess, isTrue);
    expect(c.blocksCompletedToday, 1);

    c.beginSpeak();
    now = now.add(const Duration(seconds: 4));
    c.endSpeak();
    expect(c.elapsedInBlock, const Duration(seconds: 4));

    c.giveUp();
    expect(c.sessionActive, isFalse);
    expect(c.daySuccess, isTrue);
    expect(c.blocksCompletedToday, 1);
    expect(c.elapsedInBlock, Duration.zero);

    c.startSession();
    expect(c.displayElapsed, Duration.zero);
  });

  test('streak and heat level helpers', () {
    final days = {
      '2026-09-05': 1,
      '2026-09-06': 2,
      '2026-09-07': 1,
      // gap
      '2026-09-09': 3,
    };
    expect(
      computeFocusCurrentStreak(days, todayKey: '2026-09-09'),
      1,
    );
    expect(
      computeFocusCurrentStreak(days, todayKey: '2026-09-07'),
      3,
    );
    expect(computeFocusBestStreak(days), 3);
    expect(focusHeatLevel(0), 0);
    expect(focusHeatLevel(1), 1);
    expect(focusHeatLevel(2), 2);
    expect(focusHeatLevel(5), 3);
    expect(focusStreakMilestoneReached(10), 10);
    expect(focusStreakMilestonesHit(14), [3, 7, 10, 14]);
  });
}
