/// design/418 — the practice microphone.
///
/// The phone records through its own MediaRecorder channel into an M4A file
/// (design/82); the browser records with its MediaRecorder into memory. Either
/// way a take comes back as bytes, so the practice screen has one path.
library;

import 'dart:math' as math;
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

  /// design/475 — how loud the take is right now, 0 (silence) to 1. Zero when
  /// nothing is recording or the recorder cannot tell.
  Future<double> level();

  void dispose();
}

/// design/475 — decibels below full scale where the level reads 0.
const double kMicLevelFloorDb = -50;

double _levelFromRatio(double ratio) {
  if (!ratio.isFinite || ratio <= 0) return 0;
  final db = 20 * math.log(ratio) / math.ln10;
  return ((db - kMicLevelFloorDb) / -kMicLevelFloorDb).clamp(0.0, 1.0);
}

/// The phone's MediaRecorder peak since the last read, 0..32767.
double micLevelFromAmplitude(int amplitude) => _levelFromRatio(amplitude / 32767);

/// The browser's root mean square of one frame of samples in -1..1.
double micLevelFromRms(double rms) => _levelFromRatio(rms * math.sqrt2);
