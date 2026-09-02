/// design/169o — library banner for post-ingest 재감수 (server residual only).
library;

enum HarmonizeResidualPhase {
  idle,
  arming,
  running,
  doneOk,
  donePartial,
  aborted,
}

class HarmonizeResidualSnapshot {
  const HarmonizeResidualSnapshot({
    required this.cacheId,
    required this.phase,
    required this.total,
    required this.done,
    required this.failed,
    this.attemptN = 1,
    this.abortReason = '',
  });

  final String cacheId;
  final HarmonizeResidualPhase phase;
  final int total;
  final int done;
  final int failed;
  final int attemptN;
  final String abortReason;

  bool get showProgress =>
      phase == HarmonizeResidualPhase.arming ||
      phase == HarmonizeResidualPhase.running;

  bool get showFailure =>
      phase == HarmonizeResidualPhase.donePartial ||
      phase == HarmonizeResidualPhase.aborted;

  bool get hideBanner =>
      phase == HarmonizeResidualPhase.idle ||
      phase == HarmonizeResidualPhase.doneOk;

  String get userLabel {
    switch (phase) {
      case HarmonizeResidualPhase.idle:
      case HarmonizeResidualPhase.doneOk:
        return '';
      case HarmonizeResidualPhase.arming:
        return '재감수 준비 중…';
      case HarmonizeResidualPhase.running:
        if (total < 1) return '재감수 중…';
        return '재감수 $done/$total 중';
      case HarmonizeResidualPhase.donePartial:
        if (failed > 0) return '재감수 ${failed}문장 실패';
        return '재감수 일부 실패';
      case HarmonizeResidualPhase.aborted:
        return '재감수를 이어가지 못했습니다';
    }
  }

  HarmonizeResidualSnapshot copyWith({
    HarmonizeResidualPhase? phase,
    int? total,
    int? done,
    int? failed,
    int? attemptN,
    String? abortReason,
  }) {
    return HarmonizeResidualSnapshot(
      cacheId: cacheId,
      phase: phase ?? this.phase,
      total: total ?? this.total,
      done: done ?? this.done,
      failed: failed ?? this.failed,
      attemptN: attemptN ?? this.attemptN,
      abortReason: abortReason ?? this.abortReason,
    );
  }
}

/// Map paper list / open fields → UI snapshot.
HarmonizeResidualSnapshot snapshotFromServerFields({
  required String cacheId,
  required bool pending,
  required int total,
  required int done,
  required int failed,
  int attemptN = 1,
}) {
  if (!pending && total > 0 && failed <= 0 && done >= total) {
    return HarmonizeResidualSnapshot(
      cacheId: cacheId,
      phase: HarmonizeResidualPhase.doneOk,
      total: total,
      done: done,
      failed: 0,
      attemptN: attemptN,
    );
  }
  if (!pending && failed > 0) {
    return HarmonizeResidualSnapshot(
      cacheId: cacheId,
      phase: HarmonizeResidualPhase.donePartial,
      total: total,
      done: done,
      failed: failed,
      attemptN: attemptN,
    );
  }
  if (!pending && total < 1) {
    return HarmonizeResidualSnapshot(
      cacheId: cacheId,
      phase: HarmonizeResidualPhase.idle,
      total: 0,
      done: 0,
      failed: 0,
      attemptN: attemptN,
    );
  }
  if (pending && done < 1) {
    return HarmonizeResidualSnapshot(
      cacheId: cacheId,
      phase: HarmonizeResidualPhase.arming,
      total: total,
      done: done,
      failed: failed,
      attemptN: attemptN,
    );
  }
  return HarmonizeResidualSnapshot(
    cacheId: cacheId,
    phase: HarmonizeResidualPhase.running,
    total: total,
    done: done,
    failed: failed,
    attemptN: attemptN,
  );
}
