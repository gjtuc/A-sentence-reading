/// design/422 - the web app fills the whole screen: no title bar, no taskbar.
/// The browser allows it only inside a click or key, and Esc always leaves it.
/// design/425 + 427: the main and figure windows follow each other. Leaving
/// follows at once; entering waits for one click in the other window, since one
/// click can fill only one window. design/428: F11 works like the button.
/// design/432: opening the AI window ends full screen; the next click is back.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';

import 'full_screen_stub.dart'
    if (dart.library.js_interop) 'full_screen_web.dart' as impl;

/// Whether this window is full screen now. Follows exits by Esc too.
final ValueNotifier<bool> fullScreenOn = ValueNotifier<bool>(false);

/// design/427 — the other window went full screen; the next click here does too.
final ValueNotifier<bool> fullScreenAwaitsClick = ValueNotifier<bool>(false);

DateTime? _leftAt;
DateTime? _awayAt;

bool get fullScreenSupported => impl.supported();

void _sync() {
  final on = impl.isOn();
  if (fullScreenOn.value && !on) {
    final now = DateTime.now();
    _leftAt = now;
    if (fullScreenSteppedAway(_awayAt, now)) {
      _awayAt = null;
      _comeBackOnClick();
    } else {
      impl.tellPeer(false);
    }
  }
  fullScreenOn.value = on;
  if (on) fullScreenAwaitsClick.value = false;
  if (on != _escapeHeld) {
    _escapeHeld = on;
    impl.holdEscape(on);
  }
}

bool _escapeHeld = false;

bool _watching = false;
bool _armed = false;

void _onPeer(bool on) {
  if (!on) {
    fullScreenAwaitsClick.value = false;
    unawaited(exitFullScreen());
    return;
  }
  if (fullScreenOn.value) return;
  // A click here in the last few seconds may still allow it.
  impl.enter().then((ok) {
    _sync();
    if (ok) return;
    fullScreenAwaitsClick.value = true;
    if (_armed) return;
    _armed = true;
    impl.onNextGestureSwallowed(() {
      _armed = false;
      if (!fullScreenAwaitsClick.value || fullScreenOn.value) return false;
      fullScreenAwaitsClick.value = false;
      impl.enter().then((_) => _sync());
      return true;
    });
  });
}

void _comeBackOnClick() {
  impl.onNextGestureSwallowed(() {
    if (fullScreenOn.value) return false;
    unawaited(enterFullScreen());
    return true;
  });
}

void _watch() {
  if (_watching || !fullScreenSupported) return;
  _watching = true;
  impl.onChange(_sync);
  impl.onPeer(_onPeer);
  impl.onFullScreenKey(() => unawaited(toggleFullScreen()));
  impl.onLooseEscape(() => fullScreenTakesEscape());
  _sync();
}

/// Starts listening for the other window. Call once per window on the web.
void startFullScreenSync() => _watch();

/// Must run inside a click or key. False when the browser said no. The other
/// window is told after this window has used the click.
Future<bool> enterFullScreen() async {
  _watch();
  final ok = await impl.enter();
  _sync();
  if (ok) impl.tellPeer(true);
  return ok;
}

Future<void> exitFullScreen() async {
  _watch();
  fullScreenAwaitsClick.value = false;
  await impl.exit();
  _sync();
}

Future<void> toggleFullScreen() =>
    fullScreenOn.value ? exitFullScreen() : enterFullScreen().then((_) {});

/// design/432 — this window is about to open another one, which ends its full
/// screen (measured in Chrome: a tab or a window alike). The other pane is not
/// told to leave, and the next click here enters again.
void fullScreenStepAway({DateTime? now}) {
  if (!fullScreenOn.value) return;
  _awayAt = now ?? DateTime.now();
}

/// The exit at [now] came from [fullScreenStepAway] at [awayAt], not the user.
bool fullScreenSteppedAway(DateTime? awayAt, DateTime now) {
  if (awayAt == null) return false;
  final d = now.difference(awayAt);
  return !d.isNegative && d < const Duration(seconds: 3);
}

/// design/502 — an Esc that no open window used leaves full screen. True when
/// it did, so the screen under it does not also go back.
bool fullScreenTakesEscape() {
  if (!fullScreenOn.value) return false;
  unawaited(exitFullScreen());
  return true;
}

/// The Esc that left full screen is not also a "back".
bool fullScreenJustLeft({DateTime? now}) {
  final at = _leftAt;
  if (at == null) return false;
  return (now ?? DateTime.now()).difference(at) < const Duration(milliseconds: 400);
}

/// At launch: the next click or key enters full screen. [hold] is true while
/// that click belongs to something else (the figure window still to open); the
/// try then waits for the click after. Stops when [wanted] turns false.
void enterFullScreenOnNextGesture({
  required bool Function() wanted,
  bool Function()? hold,
}) {
  _watch();
  if (!fullScreenSupported) return;
  void arm() {
    impl.onNextGesture(() {
      if (!wanted() || fullScreenOn.value) return;
      if (hold?.call() == true) {
        arm();
        return;
      }
      enterFullScreen().then((ok) {
        if (!ok && wanted() && !fullScreenOn.value) arm();
      });
    });
  }

  arm();
}

/// Opening a window can end full screen, so in the main window full screen
/// waits while the figure window is still to open on its own: not tried yet,
/// or waiting for its click.
bool fullScreenWaitsForPane({
  required bool main,
  required bool autoPane,
  required bool figureOpen,
  required bool tried,
  required bool gesturePending,
}) {
  if (!main || !autoPane || figureOpen) return false;
  return !tried || gesturePending;
}

@visibleForTesting
void markFullScreenLeftForTests(DateTime? at) => _leftAt = at;
