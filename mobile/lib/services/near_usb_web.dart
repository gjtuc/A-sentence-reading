/// design/451 — the web page's line to the PC helper: a WebSocket on 127.0.0.1.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:js_interop';
import 'dart:typed_data';

import 'package:web/web.dart' as web;

import 'near_usb_line.dart';

Future<UsbLine> connectUsbLine({required Duration timeout}) async {
  final ws = web.WebSocket('ws://127.0.0.1:$kUsbWebPort')..binaryType = 'arraybuffer';
  final line = _WebUsbLine(ws);
  try {
    await line._opened.future.timeout(timeout);
  } catch (_) {
    await line.close();
    rethrow;
  }
  return line;
}

class _WebUsbLine implements UsbLine {
  _WebUsbLine(this._ws) {
    _ws.onopen = ((web.Event _) {
      if (!_opened.isCompleted) _opened.complete();
    }).toJS;
    _ws.onerror = ((web.Event _) {
      if (!_opened.isCompleted) _opened.completeError(StateError('usb none'));
    }).toJS;
    _ws.onclose = ((web.CloseEvent _) {
      if (!_opened.isCompleted) _opened.completeError(StateError('usb none'));
      if (!_in.isClosed) unawaited(_in.close());
    }).toJS;
    _ws.onmessage = ((web.MessageEvent e) {
      if (_in.isClosed) return;
      final data = e.data;
      if (data.typeofEquals('string')) {
        try {
          final m = jsonDecode((data as JSString).toDart);
          if (m is Map) _in.add(Map<String, Object?>.from(m));
        } catch (_) {}
      } else if (data.instanceOfString('ArrayBuffer')) {
        _in.add((data as JSArrayBuffer).toDart.asUint8List());
      }
    }).toJS;
  }

  final web.WebSocket _ws;
  final _opened = Completer<void>();
  final _in = StreamController<Object>();

  @override
  Stream<Object> get incoming => _in.stream;

  @override
  void sendData(Uint8List data) {
    if (_in.isClosed) throw StateError('usb closed');
    _ws.send(data.toJS);
  }

  @override
  Future<void> close() async {
    if (!_in.isClosed) unawaited(_in.close());
    try {
      _ws.close();
    } catch (_) {}
  }
}
