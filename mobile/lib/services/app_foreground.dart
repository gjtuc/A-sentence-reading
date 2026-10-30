/// design/396 — whether the app is on screen, so polling loops stop waking the
/// server while nobody is looking.
library;

import 'dart:async';

import 'package:flutter/widgets.dart';

import 'evidence_bus.dart';

/// Off screen, a job poll asks this often. One request a minute is enough to
/// keep the instance that runs the analysis alive.
const Duration kAwayPollEvery = Duration(minutes: 1);

/// Off screen this long, polling stops until the app comes back.
const Duration kAwayPollFor = Duration(minutes: 30);

class AppForeground with WidgetsBindingObserver {
  AppForeground({DateTime Function()? clock}) : _clock = clock ?? DateTime.now;

  static final AppForeground instance = AppForeground();

  final DateTime Function() _clock;
  DateTime? _leftAt;
  Completer<void>? _back;
  bool _bound = false;

  void bind() {
    if (_bound) return;
    _bound = true;
    WidgetsBinding.instance.addObserver(this);
  }

  bool get away => _leftAt != null;

  Duration get awayFor {
    final left = _leftAt;
    return left == null ? Duration.zero : _clock().difference(left);
  }

  /// Away long enough that loops should wait for the app instead of asking.
  bool get resting => away && awayFor >= kAwayPollFor;

  /// Completes at once when on screen.
  Future<void> untilBack() {
    if (!away) return Future<void>.value();
    return (_back ??= Completer<void>()).future;
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) => onState(state);

  void onState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.resumed:
        final left = _leftAt;
        _leftAt = null;
        _back?.complete();
        _back = null;
        if (left != null) _note('back', _clock().difference(left));
      case AppLifecycleState.paused:
      case AppLifecycleState.hidden:
      case AppLifecycleState.detached:
        if (_leftAt == null) {
          _leftAt = _clock();
          _note('away', Duration.zero);
        }
      case AppLifecycleState.inactive:
        break;
    }
  }
}

/// design/487 - when the app left and came back, beside the slow polls it causes.
void _note(String stage, Duration awayFor) {
  asrEvidenceBus?.record(
    'app_visibility',
    severity: 'lifecycle',
    stage: stage,
    details: {'away_s': awayFor.inSeconds},
  );
}

/// The wait between two job polls. On screen it is [onScreenEvery]. Off screen
/// it is [kAwayPollEvery], and after [kAwayPollFor] it waits for the app.
/// Returns how long it waited for the app, zero when it did not park.
Future<Duration> pollPause(
  Duration onScreenEvery, {
  AppForeground? app,
  DateTime Function()? clock,
}) async {
  final fg = app ?? AppForeground.instance;
  final now = clock ?? DateTime.now;
  if (!fg.away) {
    await Future<void>.delayed(onScreenEvery);
    return Duration.zero;
  }
  if (fg.resting) {
    final parkedAt = now();
    await fg.untilBack();
    return now().difference(parkedAt);
  }
  await Future.any<void>([
    Future<void>.delayed(kAwayPollEvery),
    fg.untilBack(),
  ]);
  return Duration.zero;
}
