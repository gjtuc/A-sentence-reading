/// design/130 · design/134 — hang / infinite-repeat detection.
///
/// WHY: silent spinners and retry loops are product failures even without
/// thrown exceptions. Thresholds locked in design/130; upload path wiring
/// and local fail-closed abort are design/134.
library;

import 'dart:async';

typedef HangReportFn = Future<void> Function({
  required String kind,
  required String message,
  String stage,
  String? paperTitle,
  String? cacheId,
});

/// Sync local abort (cancel latch / fail UI) before cloud report.
typedef HangLocalFn = void Function(String opId, String kind);

class HangWatchdog {
  HangWatchdog({HangReportFn? onHang, HangLocalFn? onLocal})
      : _onHang = onHang,
        _onLocal = onLocal;

  HangReportFn? _onHang;
  HangLocalFn? _onLocal;

  /// Short API / open path — no completion within this → hang.
  static const shortStall = Duration(seconds: 45);

  /// Ingest / long job — no *progress* within this → hang (design/130·134).
  static const ingestStall = Duration(minutes: 3);

  /// Translate stage can sit at 90% for a long Gemini run (0.3.123).
  static const translateStall = Duration(minutes: 15);

  /// Same stage advanced with no progress this many times → loop.
  static const maxRepeatWithoutProgress = 5;

  final Map<String, _Track> _tracks = {};

  void setReporter(HangReportFn? fn) => _onHang = fn;

  void setLocalHandler(HangLocalFn? fn) => _onLocal = fn;

  /// Start or refresh a tracked op. [opId] should be stable per logical job.
  void begin(
    String opId, {
    required String stage,
    Duration stallAfter = shortStall,
    String? paperTitle,
    String? cacheId,
  }) {
    cancelTimer(opId);
    final t = _Track(
      stage: stage,
      paperTitle: paperTitle,
      cacheId: cacheId,
      stallAfter: stallAfter,
    );
    _tracks[opId] = t;
    t.timer = Timer(stallAfter, () => _fireHang(opId, t, kind: 'hang'));
  }

  /// Mark progress (resets stall clock; clears repeat counter for new stage).
  void progress(String opId, {String? stage}) {
    final t = _tracks[opId];
    if (t == null) return;
    cancelTimer(opId);
    if (stage != null && stage != t.stage) {
      t.stage = stage;
      t.repeatSame = 0;
    } else {
      // Same stage progress still counts as life — reset stall only.
      t.repeatSame = 0;
    }
    t.timer = Timer(t.stallAfter, () => _fireHang(opId, t, kind: 'hang'));
  }

  /// 0.3.123 — lengthen stall (e.g. translate) without losing track identity.
  void setStallAfter(String opId, Duration stallAfter) {
    final t = _tracks[opId];
    if (t == null) return;
    t.stallAfter = stallAfter;
    cancelTimer(opId);
    t.timer = Timer(t.stallAfter, () => _fireHang(opId, t, kind: 'hang'));
  }

  /// Record an attempt of the same stage without progress (retry loop).
  void noteRepeat(String opId, {required String stage}) {
    final t = _tracks[opId];
    if (t == null) {
      begin(opId, stage: stage);
      return;
    }
    if (t.stage == stage) {
      t.repeatSame += 1;
      if (t.repeatSame >= maxRepeatWithoutProgress) {
        _fireHang(opId, t, kind: 'repeat_loop');
      }
    } else {
      t.stage = stage;
      t.repeatSame = 1;
    }
  }

  void end(String opId) {
    cancelTimer(opId);
    _tracks.remove(opId);
  }

  void cancelTimer(String opId) {
    _tracks[opId]?.timer?.cancel();
    _tracks[opId]?.timer = null;
  }

  void dispose() {
    for (final id in _tracks.keys.toList()) {
      end(id);
    }
  }

  Future<void> _fireHang(String opId, _Track t, {required String kind}) async {
    _tracks.remove(opId);
    t.timer?.cancel();
    // WHY local first: stop in-flight upload before awaiting network report.
    _onLocal?.call(opId, kind);
    final fn = _onHang;
    if (fn == null) return;
    await fn(
      kind: kind,
      message: kind == 'repeat_loop'
          ? 'same stage repeated without progress: ${t.stage} (op=$opId)'
          : 'no progress for ${t.stallAfter.inSeconds}s at ${t.stage} (op=$opId)',
      stage: t.stage,
      paperTitle: t.paperTitle,
      cacheId: t.cacheId,
    );
  }
}

class _Track {
  _Track({
    required this.stage,
    required this.stallAfter,
    this.paperTitle,
    this.cacheId,
  });

  String stage;
  Duration stallAfter;
  final String? paperTitle;
  final String? cacheId;
  int repeatSame = 0;
  Timer? timer;
}
