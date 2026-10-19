/// design/418 — the practice microphone.
///
/// The phone records through its own MediaRecorder channel into an M4A file
/// (design/82); the browser records with its MediaRecorder into memory. Either
/// way a take comes back as bytes, so the practice screen has one path.
library;

import 'dart:typed_data';

import 'shadow_mic_io.dart' if (dart.library.js_interop) 'shadow_mic_web.dart'
    as impl;

class MicTake {
  const MicTake({
    required this.bytes,
    required this.mime,
    this.path,
    this.durationMs = -1,
  });

  final Uint8List bytes;

  /// Content type without codec parameters (`audio/mp4`, `audio/webm`).
  final String mime;

  /// The file on the phone; null in the browser.
  final String? path;

  /// Measured by the recorder; -1 when only the file can tell.
  final int durationMs;
}

abstract class ShadowMic {
  factory ShadowMic() => impl.createShadowMic();

  /// Asks once when not yet allowed.
  Future<bool> ensurePermission();

  /// Readies the next take so starting it is cheap.
  Future<bool> prepare(String tag);

  /// [usePrimed] false leaves a prepared take for the speak phase it was made for.
  Future<bool> start(String tag, {bool usePrimed = true});

  /// Null when no recording exists; empty bytes when it exists but holds nothing.
  Future<MicTake?> stop();

  /// Stops without keeping anything.
  Future<void> cancel();

  void dispose();
}
