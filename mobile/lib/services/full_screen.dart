/// design/422 - the web app fills the whole screen: no title bar, no taskbar.
/// The browser allows it only inside a click or key, and Esc always leaves it.
library;

import 'package:flutter/foundation.dart';

import 'full_screen_stub.dart'
    if (dart.library.js_interop) 'full_screen_web.dart' as impl;

/// Whether this window is full screen now. Follows exits by Esc too.
final ValueNotifier<bool> fullScreenOn = ValueNotifier<bool>(false);

DateTime? _leftAt;

bool get fullScreenSupported => impl.supported();

void _sync() {
  final on = impl.isOn();
  if (fullScreenOn.value && !on) _leftAt = DateTime.now();
  fullScreenOn.value = on;
}

bool _watching = false;

void _watch() {
  if (_watching || !fullScreenSupported) return;
  _watching = true;
  impl.onChange(_sync);
  _sync();
}

/// Must run inside a click or key. False when the browser said no.
Future<bool> enterFullScreen() async {
  _watch();
  final ok = await impl.enter();
  _sync();
  return ok;
}

Future<void> exitFullScreen() async {
  _watch();
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
