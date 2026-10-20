/// design/422 - the browser Fullscreen API. design/425: the pair of windows
/// follow each other by postMessage. design/427: measured in Chrome, one click
/// fills one window only (requestFullscreen and fullscreen delegation each use
/// up the click), so the other window is only told, and waits for its own click.
/// design/428: F11 is taken from the browser and works like the button.
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

/// Esc never carries the right to go full screen; F11 has its own handler.
bool _skipKey(web.Event e) {
  if (e.type != 'keydown') return false;
  final key = (e as web.KeyboardEvent).key;
  return key == 'Escape' || key == 'F11';
}

/// [handler] returns true when it used the press. Only then is the press
/// stopped (with its release), so the app under it does not also act on it.
void _onceOnGesture(bool Function() handler, {required bool swallow}) {
  var done = false;
  late final JSFunction listener;
  listener = ((web.Event e) {
    if (done || _skipKey(e)) return;
    done = true;
    web.window.removeEventListener('pointerdown', listener, true.toJS);
    web.window.removeEventListener('keydown', listener, true.toJS);
    final used = handler();
    if (swallow && used) {
      e.stopPropagation();
      e.preventDefault();
      if (e.type == 'pointerdown') _swallowRelease();
    }
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

void onNextGesture(void Function() handler) => _onceOnGesture(() {
      handler();
      return false;
    }, swallow: false);

void onNextGestureSwallowed(bool Function() handler) =>
    _onceOnGesture(handler, swallow: true);

/// F11 would be the browser's own full screen, which the other window never
/// hears of. Taken here, it is a key press like any other and fills this window
/// the same way as the button.
void onFullScreenKey(void Function() handler) {
  web.window.addEventListener(
    'keydown',
    ((web.KeyboardEvent e) {
      if (e.key != 'F11' || e.repeat) return;
      e.preventDefault();
      e.stopPropagation();
      handler();
    }).toJS,
    true.toJS,
  );
}

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
