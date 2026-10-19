/// design/422 - the browser Fullscreen API. design/425: the pair of windows
/// follow each other by postMessage.
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

void onNextGesture(void Function() handler) {
  var done = false;
  late final JSFunction listener;
  listener = ((web.Event _) {
    if (done) return;
    done = true;
    web.window.removeEventListener('pointerdown', listener, true.toJS);
    web.window.removeEventListener('keydown', listener, true.toJS);
    handler();
  }).toJS;
  web.window.addEventListener('pointerdown', listener, true.toJS);
  web.window.addEventListener('keydown', listener, true.toJS);
}

/// Tells the other window. An enter hands over this click's right to go full
/// screen (Chrome and Edge capability delegation); a browser without it gets a
/// plain message and the other window waits for its own click.
void tellPeer(bool on) {
  final peer = peerWindow();
  if (peer == null) return;
  final origin = web.window.location.origin;
  final msg = (on ? _kEnter : _kExit).toJS;
  if (on) {
    try {
      final opts = JSObject()
        ..setProperty('targetOrigin'.toJS, origin.toJS)
        ..setProperty('delegate'.toJS, 'fullscreen'.toJS);
      (peer as JSObject).callMethod<JSAny?>('postMessage'.toJS, msg, opts);
      return;
    } catch (_) {}
  }
  try {
    (peer as JSObject).callMethod<JSAny?>('postMessage'.toJS, msg, origin.toJS);
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
