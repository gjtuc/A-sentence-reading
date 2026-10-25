/// design/451 — the phone's line to the PC helper: TCP through `adb reverse`.
library;

import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'near_usb_line.dart';

Future<UsbLine> connectUsbLine({required Duration timeout}) async {
  final socket = await Socket.connect(
    InternetAddress.loopbackIPv4,
    kUsbPhonePort,
    timeout: timeout,
  );
  socket.setOption(SocketOption.tcpNoDelay, true);
  return _TcpUsbLine(socket);
}

class _TcpUsbLine implements UsbLine {
  _TcpUsbLine(this._socket) {
    final reader = UsbFrameReader();
    _socket.listen(
      (chunk) {
        try {
          for (final item in reader.add(chunk)) {
            if (!_in.isClosed) _in.add(item);
          }
        } catch (_) {
          unawaited(close());
        }
      },
      onError: (Object _) => unawaited(close()),
      onDone: () => unawaited(close()),
      cancelOnError: true,
    );
  }

  final Socket _socket;
  final _in = StreamController<Object>();

  @override
  Stream<Object> get incoming => _in.stream;

  @override
  void sendData(Uint8List data) {
    if (_in.isClosed) throw StateError('usb closed');
    _socket.add(encodeUsbFrame(kUsbKindData, data));
  }

  @override
  Future<void> close() async {
    if (!_in.isClosed) unawaited(_in.close());
    try {
      await _socket.flush().timeout(const Duration(seconds: 2));
    } catch (_) {}
    _socket.destroy();
  }
}
