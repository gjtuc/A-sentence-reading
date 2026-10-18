/// design/415 - BroadcastChannel and window.open for the figure window.
library;

import 'dart:convert';
import 'dart:js_interop';

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
    return web.window.open(url, name, 'popup=yes,width=1100,height=850') != null;
  } catch (_) {
    return false;
  }
}

void onPageHide(void Function() handler) {
  web.window.addEventListener('pagehide', ((web.Event _) => handler()).toJS);
}
