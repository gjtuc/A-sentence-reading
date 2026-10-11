// design/396 - polling loops rest while the app is off screen.
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/services/app_foreground.dart';

void main() {
  test('design/396 on screen by default, nothing to wait for', () async {
    final app = AppForeground();
    expect(app.away, isFalse);
    expect(app.resting, isFalse);
    await app.untilBack();
  });

  test('design/396 inactive is still on screen', () {
    final app = AppForeground();
    app.onState(AppLifecycleState.inactive);
    expect(app.away, isFalse);
  });

  test('design/396 rests after thirty minutes away', () {
    var now = DateTime(2026, 10, 11, 23);
    final app = AppForeground(clock: () => now);
    app.onState(AppLifecycleState.paused);
    expect(app.away, isTrue);
    expect(app.resting, isFalse);
    now = now.add(kAwayPollFor);
    expect(app.resting, isTrue);
    app.onState(AppLifecycleState.resumed);
    expect(app.away, isFalse);
    expect(app.resting, isFalse);
  });

  test('design/396 a second pause keeps the first leave time', () {
    var now = DateTime(2026, 10, 11, 23);
    final app = AppForeground(clock: () => now);
    app.onState(AppLifecycleState.hidden);
    now = now.add(const Duration(minutes: 20));
    app.onState(AppLifecycleState.paused);
    now = now.add(const Duration(minutes: 10));
    expect(app.resting, isTrue);
  });

  test('design/396 on screen the poll waits its own interval', () async {
    final app = AppForeground();
    final parked = await pollPause(Duration.zero, app: app);
    expect(parked, Duration.zero);
  });

  test('design/396 away but not resting, coming back ends the wait', () async {
    final app = AppForeground();
    app.onState(AppLifecycleState.paused);
    var done = false;
    final wait = pollPause(Duration.zero, app: app).then((d) {
      done = true;
      return d;
    });
    await Future<void>.delayed(const Duration(milliseconds: 20));
    expect(done, isFalse);
    app.onState(AppLifecycleState.resumed);
    expect(await wait, Duration.zero);
  });

  test('design/396 resting parks until the app is back', () async {
    var now = DateTime(2026, 10, 11, 23);
    final app = AppForeground(clock: () => now);
    app.onState(AppLifecycleState.paused);
    now = now.add(kAwayPollFor);
    var done = false;
    final wait = pollPause(Duration.zero, app: app, clock: () => now).then((d) {
      done = true;
      return d;
    });
    await Future<void>.delayed(const Duration(milliseconds: 20));
    expect(done, isFalse);
    now = now.add(const Duration(hours: 5));
    app.onState(AppLifecycleState.resumed);
    expect(await wait, const Duration(hours: 5));
  });

  test('design/396 the away poll is a minute and the cap half an hour', () {
    expect(kAwayPollEvery, const Duration(minutes: 1));
    expect(kAwayPollFor, const Duration(minutes: 30));
  });
}
