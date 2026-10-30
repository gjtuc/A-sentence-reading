// design/487 - a stalled ingest watch asks the server before it gives up.
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/services/app_foreground.dart';
import 'package:sentence_reading/services/hang_watchdog.dart';

void main() {
  test('design/487: off screen the watch never gives up', () {
    expect(ingestHangShouldAbort(away: true), isFalse);
    expect(
      ingestHangShouldAbort(away: true, server: {'ok': false, 'done': true}),
      isFalse,
    );
  });

  test('design/487: a worker that still holds the job keeps it', () {
    expect(
      ingestHangShouldAbort(
        away: false,
        server: {'ok': true, 'done': false, 'worker_alive': true, 'percent': 70},
      ),
      isFalse,
    );
    expect(
      ingestHangShouldAbort(away: false, server: {'ok': true, 'done': true}),
      isFalse,
    );
  });

  test('design/487: no answer, a dead worker or a failed job gives up', () {
    expect(ingestHangShouldAbort(away: false), isTrue);
    expect(
      ingestHangShouldAbort(
        away: false,
        server: {'ok': true, 'done': false, 'worker_alive': false},
      ),
      isTrue,
    );
    expect(ingestHangShouldAbort(away: false, server: {'ok': true}), isTrue);
    expect(
      ingestHangShouldAbort(away: false, server: {'ok': false, 'done': true}),
      isTrue,
    );
  });

  test('design/487: leaving twice keeps the first time it left', () {
    var now = DateTime(2026, 10, 30, 14, 50);
    final app = AppForeground(clock: () => now);
    app.onState(AppLifecycleState.hidden);
    now = now.add(const Duration(minutes: 2));
    app.onState(AppLifecycleState.paused);
    expect(app.awayFor, const Duration(minutes: 2));
    app.onState(AppLifecycleState.resumed);
    expect(app.away, isFalse);
  });
}
