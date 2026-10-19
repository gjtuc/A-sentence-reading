/// design/415 - BroadcastChannel and window.open for the figure window.
library;

import 'dart:convert';
import 'dart:js_interop';
import 'dart:js_interop_unsafe';

import 'package:web/web.dart' as web;

import 'pane_link.dart';

/// Messages go as JSON text so no structured-clone conversion is involved.
class _BroadcastPaneChannel implements PaneChannel {
  _BroadcastPaneChannel(String name) : _bc = web.BroadcastChannel(name);

  final web.BroadcastChannel _bc;

  @override
  void post(Map<String, Object?> message) => _bc.postMessage(jsonEncode(message).toJS);

  @override
  set onMessage(void Function(Map<String, Object?> message)? handler) {
    if (handler == null) {
      _bc.onmessage = null;
      return;
    }
    _bc.onmessage = ((web.MessageEvent e) {
      final raw = e.data.dartify();
      if (raw is! String) return;
      try {
        final m = jsonDecode(raw);
        if (m is Map<String, Object?>) handler(m);
      } catch (_) {}
    }).toJS;
  }

  @override
  void close() => _bc.close();
}

PaneChannel? openPaneChannel(String name) {
  try {
    return _BroadcastPaneChannel(name);
  } catch (_) {
    return null;
  }
}

bool openWindow(String url, String name) {
  try {
    return web.window.open(url, name, _features()) != null;
  } catch (_) {
    return false;
  }
}

void onPageHide(void Function() handler) {
  web.window.addEventListener('pagehide', ((web.Event _) => handler()).toJS);
}

void closeWindow() {
  try {
    web.window.close();
  } catch (_) {}
}

@JS('getScreenDetails')
external JSPromise<JSObject> _getScreenDetails();

/// The browser's live ScreenDetails, once allowed (Chrome and Edge).
JSObject? _screens;

Future<bool> prepareScreens({bool ask = false}) async {
  if (!(web.window as JSObject).has('getScreenDetails')) return false;
  try {
    if (!ask) {
      final desc = JSObject()..setProperty('name'.toJS, 'window-management'.toJS);
      final st = await web.window.navigator.permissions.query(desc).toDart;
      if (st.state != 'granted') return false;
    }
    _screens = await _getScreenDetails().toDart;
    return true;
  } catch (_) {
    return false;
  }
}

PaneScreen _screen(JSObject s) {
  int n(String k) => s.getProperty<JSNumber>(k.toJS).toDartDouble.round();
  return (
    left: n('availLeft'),
    top: n('availTop'),
    width: n('availWidth'),
    height: n('availHeight'),
  );
}

String _features() {
  final d = _screens;
  if (d == null) return paneWindowFeatures(const [], null);
  try {
    final all = d.getProperty<JSArray<JSObject>>('screens'.toJS).toDart;
    final current = d.getProperty<JSObject>('currentScreen'.toJS);
    return paneWindowFeatures([for (final s in all) _screen(s)], _screen(current));
  } catch (_) {
    return paneWindowFeatures(const [], null);
  }
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
