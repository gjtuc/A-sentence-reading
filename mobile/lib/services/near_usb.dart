/// design/451 — near sync over the USB cable, through the PC helper.
///
/// Both sides first try the helper. It says in `hello` whether a phone is on the
/// cable (`cable`) and who is already there, and `paired` once both are. After
/// that the near-sync frames pass unchanged, so [NearSync] runs as on any pipe.
library;

import 'dart:async';
import 'dart:typed_data';

import 'near_sync.dart';
import 'near_usb_line.dart';
import 'near_usb_io.dart' if (dart.library.js_interop) 'near_usb_web.dart';

const Duration kUsbConnectLimit = Duration(milliseconds: 1500);
const Duration kUsbHelloLimit = Duration(milliseconds: 1500);

typedef UsbOpen = Future<NearUsbSession?> Function();

class NearUsbSession {
  NearUsbSession(this.line) {
    _hello.future.ignore();
    _paired.future.ignore();
    _sub = line.incoming.listen(
      _on,
      onError: (Object _) => _end(),
      onDone: _end,
    );
  }

  final UsbLine line;
  final _hello = Completer<Map<String, Object?>>();
  final _paired = Completer<void>();
  final _data = StreamController<Uint8List>();
  StreamSubscription<Object>? _sub;
  Map<String, Object?> _info = const {};

  Future<Map<String, Object?>> get hello => _hello.future;
  Future<void> get paired => _paired.future;
  bool get isPaired => _paired.isCompleted;

  /// A phone is attached with USB debugging allowed.
  bool get cable => _info['cable'] == true;

  /// The web page is already waiting at the helper.
  bool get webThere => _info['web'] == true;

  late final NearPipe pipe = _UsbPipe(this);

  void _on(Object item) {
    if (item is Uint8List) {
      if (!_data.isClosed) _data.add(item);
      return;
    }
    if (item is! Map) return;
    switch (item['t']) {
      case 'hello':
        _info = Map<String, Object?>.from(item);
        if (!_hello.isCompleted) _hello.complete(_info);
      case 'paired':
        if (!_paired.isCompleted) _paired.complete();
    }
  }

  void _end() {
    if (!_hello.isCompleted) _hello.completeError(const NearSyncError('usb_gone'));
    if (!_paired.isCompleted) _paired.completeError(const NearSyncError('usb_gone'));
    if (!_data.isClosed) unawaited(_data.close());
  }

  Future<void> close() async {
    _end();
    await _sub?.cancel();
    await line.close();
  }
}

class _UsbPipe implements NearPipe {
  _UsbPipe(this.session);

  final NearUsbSession session;

  @override
  Stream<Uint8List> get frames => session._data.stream;

  @override
  Future<void> send(Uint8List frame) async => session.line.sendData(frame);
}

/// The helper's session after its `hello`, or null when no helper answers.
Future<NearUsbSession?> openNearUsb({
  Future<UsbLine> Function({required Duration timeout})? connect,
}) async {
  UsbLine line;
  try {
    line = await (connect ?? connectUsbLine)(timeout: kUsbConnectLimit);
  } catch (_) {
    return null;
  }
  final session = NearUsbSession(line);
  try {
    await session.hello.timeout(kUsbHelloLimit);
    return session;
  } catch (_) {
    await session.close();
    return null;
  }
}
