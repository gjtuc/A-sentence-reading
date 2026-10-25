/// design/451 — one connection to the PC's USB sync helper
/// (`scripts/usb_sync_bridge.py`).
///
/// The web page uses a WebSocket on [kUsbWebPort]. The phone uses plain TCP on
/// [kUsbPhonePort], which `adb reverse` carries over the cable; plain TCP because
/// the app allows no cleartext HTTP (design/138) and a WebSocket is HTTP.
library;

import 'dart:convert';
import 'dart:typed_data';

const int kUsbWebPort = 47815;
const int kUsbPhonePort = 47816;
const int kUsbKindControl = 0;
const int kUsbKindData = 1;
const int kUsbMaxFrame = 8 * 1024 * 1024;

/// Incoming items are a control `Map<String, Object?>` or data `Uint8List`.
abstract class UsbLine {
  Stream<Object> get incoming;
  void sendData(Uint8List data);
  Future<void> close();
}

/// Phone framing: [u32 big-endian length][kind byte][payload].
Uint8List encodeUsbFrame(int kind, Uint8List payload) {
  final out = Uint8List(payload.length + 5);
  ByteData.sublistView(out).setUint32(0, payload.length + 1);
  out[4] = kind;
  out.setRange(5, out.length, payload);
  return out;
}

/// Cuts a TCP byte stream back into control maps and data frames.
class UsbFrameReader {
  final _buf = BytesBuilder(copy: false);
  Uint8List _pending = Uint8List(0);

  /// Items completed by [chunk]; throws [FormatException] on a broken stream.
  List<Object> add(List<int> chunk) {
    _buf
      ..add(_pending)
      ..add(chunk is Uint8List ? chunk : Uint8List.fromList(chunk));
    final all = _buf.takeBytes();
    final out = <Object>[];
    var at = 0;
    while (all.length - at >= 4) {
      final n = ByteData.sublistView(all, at, at + 4).getUint32(0);
      if (n < 1 || n > kUsbMaxFrame) throw const FormatException('usb frame');
      if (all.length - at - 4 < n) break;
      final kind = all[at + 4];
      final payload = Uint8List.fromList(Uint8List.sublistView(all, at + 5, at + 4 + n));
      at += 4 + n;
      if (kind == kUsbKindData) {
        out.add(payload);
      } else if (kind == kUsbKindControl) {
        final m = jsonDecode(utf8.decode(payload));
        if (m is Map) out.add(Map<String, Object?>.from(m));
      }
    }
    _pending = Uint8List.fromList(Uint8List.sublistView(all, at));
    return out;
  }
}
