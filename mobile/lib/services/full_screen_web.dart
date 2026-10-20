/// design/422 - the browser Fullscreen API. design/425: the pair of windows
/// follow each other by postMessage. design/427: measured in Chrome, one click
/// fills one window only (requestFullscreen and fullscreen delegation each use
/// up the click), so the other window is only told, and waits for its own click.
library;

import 'dart:js_interop';
import 'dart:js_interop_unsafe';

import 'package:web/web.dart' as web;

import 'pane_window_web.dart' show peerWindow;

const String _kEnter = 'asr_full_screen_enter';
const String _kExit = 'asr_full_screen_exit';

bool supported() => web.document.fullscreenEnabled;

bool isOn() => web.document.fullscreenElement != null;

void onChange(void Function() handler) {
  web.document.addEventListener('fullscreenchange', ((web.Event _) => handler()).toJS);
}

Future<bool> enter() async {
  final root = web.document.documentElement;
  if (root == null) return false;
  try {
    await root.requestFullscreen().toDart;
    return true;
  } catch (_) {
    return false;
  }
}

Future<void> exit() async {
  if (!isOn()) return;
  try {
    await web.document.exitFullscreen().toDart;
  } catch (_) {}
}

void _onceOnGesture(void Function() handler, {required bool swallow}) {
  var done = false;
  late final JSFunction listener;
  listener = ((web.Event e) {
    if (done) return;
    if (e.type == 'keydown' && (e as web.KeyboardEvent).key == 'Escape') return;
    done = true;
    web.window.removeEventListener('pointerdown', listener, true.toJS);
    web.window.removeEventListener('keydown', listener, true.toJS);
    if (swallow) {
      e.stopPropagation();
      e.preventDefault();
      if (e.type == 'pointerdown') _swallowRelease();
    }
    handler();
  }).toJS;
  web.window.addEventListener('pointerdown', listener, true.toJS);
  web.window.addEventListener('keydown', listener, true.toJS);
}

/// The release of a swallowed press, so the app never sees half a click.
void _swallowRelease() {
  late final JSFunction stop;
  stop = ((web.Event e) {
    e.stopPropagation();
    if (e.type == 'click') {
      web.window.removeEventListener('pointerup', stop, true.toJS);
      web.window.removeEventListener('click', stop, true.toJS);
    }
  }).toJS;
  web.window.addEventListener('pointerup', stop, true.toJS);
  web.window.addEventListener('click', stop, true.toJS);
  // A press dragged off the page never clicks; stop listening anyway.
  web.window.setTimeout(
    (() {
      web.window.removeEventListener('pointerup', stop, true.toJS);
      web.window.removeEventListener('click', stop, true.toJS);
    }).toJS,
    1500.toJS,
  );
}

void onNextGesture(void Function() handler) => _onceOnGesture(handler, swallow: false);

/// The click only brings full screen; the app under it does not see it.
void onNextGestureSwallowed(void Function() handler) =>
    _onceOnGesture(handler, swallow: true);

void tellPeer(bool on) {
  final peer = peerWindow();
  if (peer == null) return;
  try {
    (peer as JSObject).callMethod<JSAny?>(
      'postMessage'.toJS,
      (on ? _kEnter : _kExit).toJS,
      web.window.location.origin.toJS,
    );
  } catch (_) {}
}

void onPeer(void Function(bool on) handler) {
  web.window.addEventListener(
    'message',
    ((web.MessageEvent e) {
      if (e.origin != web.window.location.origin) return;
      final d = e.data.dartify();
      if (d == _kEnter) handler(true);
      if (d == _kExit) handler(false);
    }).toJS,
  );
}
