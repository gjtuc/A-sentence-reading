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

web.Window? _opened;

bool openWindow(String url, String name) {
  try {
    _opened = web.window.open(url, name, _features());
    return _opened != null;
  } catch (_) {
    return false;
  }
}

/// design/425 - the other window of the pair: the figure window this one
/// opened, else the main window that opened this one.
web.Window? peerWindow() {
  final w = _opened;
  if (w != null && !w.closed) return w;
  final o = web.window.opener;
  if (o == null) return null;
  try {
    final win = o as web.Window;
    return win.closed ? null : win;
  } catch (_) {
    return null;
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

({List<PaneScreen> all, PaneScreen? current}) _known() {
  final d = _screens;
  if (d == null) return (all: const [], current: null);
  try {
    final all = d.getProperty<JSArray<JSObject>>('screens'.toJS).toDart;
    final current = d.getProperty<JSObject>('currentScreen'.toJS);
    return (all: [for (final s in all) _screen(s)], current: _screen(current));
  } catch (_) {
    return (all: const [], current: null);
  }
}

String _features() {
  final k = _known();
  return paneWindowFeatures(k.all, k.current);
}

PaneScreen? otherScreen() {
  final k = _known();
  return paneTargetScreen(k.all, k.current);
}

void fillScreen(PaneScreen s) {
  try {
    web.window.moveTo(s.left, s.top);
    web.window.resizeTo(s.width, s.height);
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
