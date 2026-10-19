/// design/422 - the browser Fullscreen API.
library;

import 'dart:js_interop';

import 'package:web/web.dart' as web;

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
