/// design/208 — pure policy for practice process grooming (no Flutter).
library;

import 'dart:math';

enum GroomingSignal {
  none,
  takeFail,
  takeTooShort,
  micPerm,
  clean,
}

enum GroomingActionKind {
  none,
  rateNudge,
}

class GroomingObservation {
  const GroomingObservation({
    required this.signal,
    required this.chunkKey,
    this.code = '',
  });

  final GroomingSignal signal;
  final String chunkKey;
  final String code;
}

class GroomingDecision {
  const GroomingDecision({
    required this.action,
    required this.applied,
    this.rateScale = 1.0,
    this.skipReason = '',
    this.signal = GroomingSignal.none,
  });

  final GroomingActionKind action;
  final bool applied;
  final double rateScale;
  final String skipReason;
  final GroomingSignal signal;
}

class GroomingMemory {
  int interventionsThisSession = 0;
  int cleanStreak = 0;
  int suppressRemaining = 0;
  final List<int> interventionChunkSeq = [];
  double? pendingRateScale;
  int chunkSeq = 0;
}

/// Locked knobs from design/208.
class GroomingPolicy {
  GroomingPolicy({Random? random, double Function()? applyRoll})
      : _random = random ?? Random(),
        _applyRoll = applyRoll;

  static const int maxPerSession = 2;
  static const int rollingWindow = 5;
  static const int maxPerRolling = 1;
  static const double applyProbability = 0.45;
  static const double rateScale = 0.90;
  static const int fadeCleanStreak = 2;
  static const int fadeSuppressChunks = 6;

  final Random _random;
  final double Function()? _applyRoll;

  double _roll() => _applyRoll?.call() ?? _random.nextDouble();

  /// Consume pending scale for this cycle (one-shot).
  double beginCycle(GroomingMemory mem) {
    mem.chunkSeq += 1;
    if (mem.suppressRemaining > 0) {
      mem.suppressRemaining -= 1;
    }
    final scale = mem.pendingRateScale;
    mem.pendingRateScale = null;
    if (scale == null || scale >= 0.999) return 1.0;
    return scale;
  }

  GroomingDecision onOutcome({
    required GroomingMemory mem,
    required GroomingObservation obs,
    required bool enabled,
  }) {
    if (!enabled) {
      return GroomingDecision(
        action: GroomingActionKind.none,
        applied: false,
        skipReason: 'disabled',
        signal: obs.signal,
      );
    }

    if (obs.signal == GroomingSignal.micPerm) {
      return GroomingDecision(
        action: GroomingActionKind.none,
        applied: false,
        skipReason: 'mic_perm_observe_only',
        signal: obs.signal,
      );
    }

    if (obs.signal == GroomingSignal.clean) {
      mem.cleanStreak += 1;
      if (mem.cleanStreak >= fadeCleanStreak) {
        mem.suppressRemaining = fadeSuppressChunks;
        mem.cleanStreak = 0;
      }
      return GroomingDecision(
        action: GroomingActionKind.none,
        applied: false,
        skipReason: 'clean',
        signal: obs.signal,
      );
    }

    if (obs.signal != GroomingSignal.takeFail &&
        obs.signal != GroomingSignal.takeTooShort) {
      return GroomingDecision(
        action: GroomingActionKind.none,
        applied: false,
        skipReason: 'no_signal',
        signal: obs.signal,
      );
    }

    mem.cleanStreak = 0;

    if (mem.suppressRemaining > 0) {
      return GroomingDecision(
        action: GroomingActionKind.rateNudge,
        applied: false,
        skipReason: 'fade_suppress',
        signal: obs.signal,
      );
    }
    if (mem.interventionsThisSession >= maxPerSession) {
      return GroomingDecision(
        action: GroomingActionKind.rateNudge,
        applied: false,
        skipReason: 'session_cap',
        signal: obs.signal,
      );
    }
    final recent = mem.interventionChunkSeq
        .where((s) => mem.chunkSeq - s < rollingWindow)
        .length;
    if (recent >= maxPerRolling) {
      return GroomingDecision(
        action: GroomingActionKind.rateNudge,
        applied: false,
        skipReason: 'rolling_cap',
        signal: obs.signal,
      );
    }
    if (_roll() >= applyProbability) {
      return GroomingDecision(
        action: GroomingActionKind.rateNudge,
        applied: false,
        skipReason: 'stochastic_skip',
        signal: obs.signal,
      );
    }

    mem.pendingRateScale = rateScale;
    mem.interventionsThisSession += 1;
    mem.interventionChunkSeq.add(mem.chunkSeq);
    return GroomingDecision(
      action: GroomingActionKind.rateNudge,
      applied: true,
      rateScale: rateScale,
      skipReason: '',
      signal: obs.signal,
    );
  }

  void resetSession(GroomingMemory mem) {
    mem.interventionsThisSession = 0;
    mem.cleanStreak = 0;
    mem.suppressRemaining = 0;
    mem.interventionChunkSeq.clear();
    mem.pendingRateScale = null;
    mem.chunkSeq = 0;
  }
}
