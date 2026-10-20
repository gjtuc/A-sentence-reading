/// design/422 - the web app fills the whole screen: no title bar, no taskbar.
/// The browser allows it only inside a click or key, and Esc always leaves it.
/// design/425 + 427: the main and figure windows follow each other. Leaving
/// follows at once; entering waits for one click in the other window, since one
/// click can fill only one window.
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

bool get fullScreenSupported => impl.supported();

void _sync() {
  final on = impl.isOn();
  if (fullScreenOn.value && !on) {
    _leftAt = DateTime.now();
    impl.tellPeer(false);
  }
  fullScreenOn.value = on;
  if (on) fullScreenAwaitsClick.value = false;
}

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
      if (!fullScreenAwaitsClick.value || fullScreenOn.value) return;
      fullScreenAwaitsClick.value = false;
      impl.enter().then((_) => _sync());
    });
  });
}

void _watch() {
  if (_watching || !fullScreenSupported) return;
  _watching = true;
  impl.onChange(_sync);
  impl.onPeer(_onPeer);
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
