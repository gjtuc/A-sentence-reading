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

const String _kPairHello = 'asr_pair_hello';

/// design/426 - the window that last said [_kPairHello] here: the live figure
/// window. The `window.open` result alone did not reach it from the main window.
web.Window? _heard;
bool _listening = false;

void _listenForPair() {
  if (_listening) return;
  _listening = true;
  web.window.addEventListener(
    'message',
    ((web.MessageEvent e) {
      if (e.origin != web.window.location.origin) return;
      if (e.data.dartify() != _kPairHello) return;
      final src = e.source;
      if (src == null) return;
      try {
        _heard = src as web.Window;
      } catch (_) {}
    }).toJS,
  );
}

web.Window? _opener() {
  final o = web.window.opener;
  if (o == null) return null;
  try {
    return o as web.Window;
  } catch (_) {
    return null;
  }
}

/// Main window: listen for the figure window. Figure window: say hello to the
/// main window that opened it, so it learns where to post.
void startPair({required bool figure}) {
  _listenForPair();
  if (!figure) return;
  final o = _opener();
  if (o == null) return;
  try {
    (o as JSObject).callMethod<JSAny?>(
      'postMessage'.toJS,
      _kPairHello.toJS,
      web.window.location.origin.toJS,
    );
  } catch (_) {}
}

bool _live(web.Window? w) {
  if (w == null) return false;
  try {
    return !w.closed;
  } catch (_) {
    return false;
  }
}

/// design/425 - the other window of the pair: the figure window that said
/// hello, else the one this window opened, else the main window that opened
/// this one.
web.Window? peerWindow() {
  if (_live(_heard)) return _heard;
  if (_live(_opened)) return _opened;
  final o = _opener();
  return _live(o) ? o : null;
}

void onPageHide(void Function() handler) {
  web.window.addEventListener('pagehide', ((web.Event _) => handler()).toJS);
}

bool pageHidden() {
  try {
    return web.document.hidden;
  } catch (_) {
    return false;
  }
}

void onVisibilityChange(void Function() handler) {
  web.document.addEventListener('visibilitychange', ((web.Event _) => handler()).toJS);
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
