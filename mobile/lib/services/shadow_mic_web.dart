import 'dart:async';
import 'dart:js_interop';
import 'dart:js_interop_unsafe';

import 'package:web/web.dart' as web;

import 'shadow_mic.dart';

ShadowMic createShadowMic() => _BrowserMic();

/// First the browser can make. Chrome and Edge make WebM/Opus, Safari MP4.
const _kMimes = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/mp4',
  'audio/ogg;codecs=opus',
];

class _BrowserMic implements ShadowMic {
  web.MediaStream? _stream;
  web.MediaRecorder? _rec;
  Completer<void>? _done;
  final List<JSAny> _parts = [];
  final Stopwatch _clock = Stopwatch();

  /// The microphone stays open for the practice screen, so each take starts at
  /// once. Raw sound, like the phone's MIC source: the guide voice is silent
  /// while the user speaks, and processing would change what the model hears.
  Future<web.MediaStream?> _open() async {
    final held = _stream;
    if (held != null && held.active) return held;
    try {
      final audio = JSObject()
        ..setProperty('echoCancellation'.toJS, false.toJS)
        ..setProperty('noiseSuppression'.toJS, false.toJS)
        ..setProperty('autoGainControl'.toJS, false.toJS);
      _stream = await web.window.navigator.mediaDevices
          .getUserMedia(web.MediaStreamConstraints(audio: audio))
          .toDart;
    } catch (_) {
      _stream = null;
    }
    return _stream;
  }

  @override
  Future<bool> ensurePermission() async => await _open() != null;

  @override
  Future<bool> prepare(String tag) async => await _open() != null;

  @override
  Future<bool> start(String tag, {bool usePrimed = true}) async {
    final stream = await _open();
    if (stream == null) return false;
    _drop();
    var mime = '';
    for (final m in _kMimes) {
      if (web.MediaRecorder.isTypeSupported(m)) {
        mime = m;
        break;
      }
    }
    try {
      final rec = mime.isEmpty
          ? web.MediaRecorder(stream)
          : web.MediaRecorder(stream, web.MediaRecorderOptions(mimeType: mime));
      final done = Completer<void>();
      rec.ondataavailable = ((web.BlobEvent e) {
        if (e.data.size > 0) _parts.add(e.data);
      }).toJS;
      rec.onstop = ((web.Event _) {
        if (!done.isCompleted) done.complete();
      }).toJS;
      rec.start();
      _rec = rec;
      _done = done;
      _clock
        ..reset()
        ..start();
      return true;
    } catch (_) {
      _rec = null;
      _done = null;
      return false;
    }
  }

  @override
  Future<MicTake?> stop() async {
    final rec = _rec;
    final done = _done;
    _rec = null;
    _done = null;
    if (rec == null || done == null) return null;
    _clock.stop();
    try {
      if (rec.state != 'inactive') rec.stop();
      await done.future.timeout(const Duration(seconds: 3));
    } catch (_) {}
    final type = rec.mimeType.isEmpty ? 'audio/webm' : rec.mimeType;
    final blob = web.Blob(_parts.toJS, web.BlobPropertyBag(type: type));
    _parts.clear();
    final buf = await blob.arrayBuffer().toDart;
    return MicTake(
      bytes: buf.toDart.asUint8List(),
      mime: type.split(';').first.trim(),
      durationMs: _clock.elapsedMilliseconds,
    );
  }

  void _drop() {
    final rec = _rec;
    _rec = null;
    _done = null;
    _parts.clear();
    if (rec == null) return;
    rec.ondataavailable = null;
    try {
      if (rec.state != 'inactive') rec.stop();
    } catch (_) {}
  }

  @override
  Future<void> cancel() async => _drop();

  @override
  void dispose() {
    _drop();
    final stream = _stream;
    _stream = null;
    if (stream == null) return;
    for (final t in stream.getTracks().toDart) {
      t.stop();
    }
  }
}
