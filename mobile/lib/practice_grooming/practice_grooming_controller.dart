/// design/208 — session facade for practice process grooming.
library;

import '../services/evidence_bus.dart';
import 'grooming_policy.dart';

class PracticeGroomingController {
  PracticeGroomingController({GroomingPolicy? policy})
      : _policy = policy ?? GroomingPolicy();

  final GroomingPolicy _policy;
  final GroomingMemory _mem = GroomingMemory();

  /// Server kill: missing/true → on; explicit false → off.
  bool serverEnabled = true;

  double _cycleScale = 1.0;

  bool get enabled => serverEnabled;

  double get cycleRateScale => _cycleScale;

  void setServerEnabled(bool on) {
    serverEnabled = on;
  }

  void resetSession() {
    _policy.resetSession(_mem);
    _cycleScale = 1.0;
  }

  /// Call at the start of each practice cycle. Returns playback rate multiplier.
  double beginCycle({
    required String chunkKey,
    String? cacheId,
  }) {
    if (!enabled) {
      _cycleScale = 1.0;
      return 1.0;
    }
    _cycleScale = _policy.beginCycle(_mem);
    if (_cycleScale < 0.999) {
      asrEvidenceBus?.record(
        'practice_grooming_decision',
        cacheId: cacheId ?? '',
        ok: true,
        details: {
          'phase': 'apply_cycle',
          'chunk_key': chunkKey,
          'action': 'rate_nudge',
          'applied': 1,
          'scale': _cycleScale,
        },
      );
    }
    return _cycleScale;
  }

  void onOutcome({
    required GroomingObservation obs,
    String? cacheId,
  }) {
    final decision = _policy.onOutcome(
      mem: _mem,
      obs: obs,
      enabled: enabled,
    );
    asrEvidenceBus?.record(
      'practice_grooming_decision',
      cacheId: cacheId ?? '',
      ok: true,
      details: {
        'phase': 'outcome',
        'chunk_key': obs.chunkKey,
        'signal': obs.signal.name,
        'code': obs.code,
        'action': decision.action.name,
        'applied': decision.applied ? 1 : 0,
        'skip_reason': decision.skipReason,
        'scale': decision.rateScale,
        'session_count': _mem.interventionsThisSession,
      },
    );
  }
}
