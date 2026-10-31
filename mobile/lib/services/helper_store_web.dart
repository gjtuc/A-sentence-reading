/// design/495 — the web page's line to the helper's /store, kept quiet.
///
/// A page that opens a socket to 127.0.0.1 makes Chrome and Edge ask for the
/// "local network devices" permission. So the page only tries on its own when
/// that permission is already granted, when the browser has no such prompt,
/// or after this browser met the helper (or the user opened the guide).
library;

import 'dart:async';
import 'dart:convert';
import 'dart:js_interop';
import 'dart:js_interop_unsafe';
import 'dart:typed_data';

import 'package:web/web.dart' as web;

import 'helper_store.dart';

const String _seenKey = 'asr_helper_seen';

bool _seen() {
  try {
    return web.window.localStorage.getItem(_seenKey) == '1';
  } catch (_) {
    return false;
  }
}

/// The user opened the helper guide: trying from now on is expected.
void markHelperWanted() {
  try {
    web.window.localStorage.setItem(_seenKey, '1');
  } catch (_) {}
}

bool get _chromium =>
    web.window.navigator.getProperty<JSAny?>('userAgentData'.toJS) != null;

/// granted / denied / prompt, or '' when the browser knows no such permission.
Future<String> _localNetworkState() async {
  for (final name in ['loopback-network', 'local-network-access', 'local-network']) {
    try {
      final desc = {'name': name}.jsify()! as JSObject;
      final st = await web.window.navigator.permissions
          .query(desc)
          .toDart
          .timeout(const Duration(seconds: 2));
      return st.state;
    } catch (_) {}
  }
  return '';
}

Future<bool> _mayTryQuietly() async {
  final state = await _localNetworkState();
  if (state == 'granted') return true;
  if (state == 'denied') return false;
  if (state == '') return !_chromium || _seen();
  return _seen();
}

typedef _Socket = ({
  web.WebSocket ws,
  Future<void> opened,
  Stream<Object> incoming,
});

_Socket _openSocket(String path) {
  final ws = web.WebSocket('ws://127.0.0.1:$kHelperStorePort$path')
    ..binaryType = 'arraybuffer';
  final opened = Completer<void>();
  final incoming = StreamController<Object>();
  ws.onopen = ((web.Event _) {
    if (!opened.isCompleted) opened.complete();
  }).toJS;
  ws.onerror = ((web.Event _) {
    if (!opened.isCompleted) opened.completeError(const HelperStoreError('none'));
  }).toJS;
  ws.onclose = ((web.CloseEvent _) {
    if (!opened.isCompleted) opened.completeError(const HelperStoreError('none'));
    if (!incoming.isClosed) unawaited(incoming.close());
  }).toJS;
  ws.onmessage = ((web.MessageEvent e) {
    if (incoming.isClosed) return;
    final data = e.data;
    if (data.typeofEquals('string')) {
      try {
        final m = jsonDecode((data as JSString).toDart);
        if (m is Map) incoming.add(Map<String, Object?>.from(m));
      } catch (_) {}
    } else if (data.instanceOfString('ArrayBuffer')) {
      incoming.add((data as JSArrayBuffer).toDart.asUint8List());
    }
  }).toJS;
  return (ws: ws, opened: opened.future, incoming: incoming.stream);
}

void _closeSocket(web.WebSocket ws) {
  try {
    ws.close();
  } catch (_) {}
}

/// The open /store line and the helper's hello, or null (not running, not
/// allowed to try quietly, or an old helper without the store).
Future<(HelperLine, Map<String, Object?>)?> connectHelperStore({
  bool ask = false,
}) async {
  if (!ask && !await _mayTryQuietly()) return null;
  final (:ws, :opened, :incoming) = _openSocket('/store');
  final line = HelperLine(
    incoming: incoming,
    sendText: (t) => ws.send(t.toJS),
    sendBinary: (Uint8List b) => ws.send(b.toJS),
    close: () async => _closeSocket(ws),
  );
  try {
    await opened.timeout(kHelperOpenLimit);
    final hello = await line.hello();
    if (hello['store'] != true) {
      await line.close();
      return null;
    }
    markHelperWanted();
    return (line, hello);
  } catch (_) {
    await line.close();
    return null;
  }
}

/// design/496 — held open while the page is open, so the helper can tell the
/// phone a web page is there and tell the page when the phone arrives. Null
/// when not allowed to try quietly, not running, or a helper before version 2.
Future<HelperWatch?> connectHelperWatch() async {
  if (!await _mayTryQuietly()) return null;
  final (:ws, :opened, :incoming) = _openSocket('/watch');
  final maps = incoming
      .where((m) => m is Map<String, Object?>)
      .cast<Map<String, Object?>>()
      .asBroadcastStream();
  try {
    await opened.timeout(kHelperOpenLimit);
    final hello = await maps.first.timeout(kHelperOpenLimit);
    if (hello['t'] != 'hello') throw const HelperStoreError('no_hello');
    markHelperWanted();
    return HelperWatch(hello: hello, messages: maps, close: () async => _closeSocket(ws));
  } catch (_) {
    _closeSocket(ws);
    return null;
  }
}

/// The phone's check; the web asks [connectHelperStore] instead.
Future<Map<String, Object?>?> probeHelperFromPhone() async => null;

/// Ask the browser not to clear this site's storage when the disk fills up.
/// Chrome, Edge and Safari decide silently; Firefox would show a prompt, so it
/// is skipped there.
Future<void> askBrowserToKeepStorage() async {
  try {
    if (web.window.navigator.userAgent.contains('Firefox')) return;
    final storage = web.window.navigator.storage;
    if ((await storage.persisted().toDart).toDart) return;
    await storage.persist().toDart;
  } catch (_) {}
}
