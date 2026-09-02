/// design/169n — library-tab background figure byte hydrate (not translate).
///
/// User-visible progress only; evidence kinds carry miss/abort detail.
library;

/// Coarse hydrate phase for one [cacheId].
enum FigureHydratePhase {
  idle,
  arming,
  hydrating,
  doneOk,
  donePartial,
  aborted,
}

/// Snapshot for library row UI + tests (no paper text).
class FigureHydrateSnapshot {
  const FigureHydrateSnapshot({
    required this.cacheId,
    required this.phase,
    required this.total,
    required this.filled,
    required this.failed,
    this.attemptN = 1,
    this.abortReason = '',
  });

  final String cacheId;
  final FigureHydratePhase phase;
  final int total;
  final int filled;
  final int failed;
  final int attemptN;
  final String abortReason;

  bool get showProgress =>
      phase == FigureHydratePhase.arming || phase == FigureHydratePhase.hydrating;

  bool get showFailure =>
      phase == FigureHydratePhase.donePartial || phase == FigureHydratePhase.aborted;

  bool get hideBanner =>
      phase == FigureHydratePhase.idle || phase == FigureHydratePhase.doneOk;

  /// Honest Korean label for library row; empty when banner should hide.
  String get userLabel {
    switch (phase) {
      case FigureHydratePhase.idle:
      case FigureHydratePhase.doneOk:
        return '';
      case FigureHydratePhase.arming:
        return total > 0 ? '그림 준비 중…' : '그림 준비 중…';
      case FigureHydratePhase.hydrating:
        if (total < 1) return '그림 받는 중…';
        return '그림 $filled/$total 받는 중';
      case FigureHydratePhase.donePartial:
        if (failed > 0) return '그림 ${failed}장 받지 못함';
        return '그림 일부 받지 못함';
      case FigureHydratePhase.aborted:
        return '그림을 준비하지 못했습니다';
    }
  }

  FigureHydrateSnapshot copyWith({
    FigureHydratePhase? phase,
    int? total,
    int? filled,
    int? failed,
    int? attemptN,
    String? abortReason,
  }) {
    return FigureHydrateSnapshot(
      cacheId: cacheId,
      phase: phase ?? this.phase,
      total: total ?? this.total,
      filled: filled ?? this.filled,
      failed: failed ?? this.failed,
      attemptN: attemptN ?? this.attemptN,
      abortReason: abortReason ?? this.abortReason,
    );
  }
}

/// Counts how many figures already have a non-empty [imageSrc]-like field.
int countFilledFromSrcList(Iterable<String> imageSrcs) {
  var n = 0;
  for (final s in imageSrcs) {
    if (s.trim().isNotEmpty) n++;
  }
  return n;
}

/// Centers to visit with span=1 so every index is covered with fewer calls.
List<int> hydrateCenters({required int total, int span = 1}) {
  if (total < 1) return const [];
  if (span <= 0) {
    return [for (var i = 0; i < total; i++) i];
  }
  final step = span * 2 + 1;
  final out = <int>[];
  for (var c = 0; c < total; c += step) {
    out.add(c);
  }
  // Ensure last index is covered when step skips the end.
  final last = total - 1;
  if (out.isEmpty || out.last != last) {
    final need = last - span;
    if (need >= 0 && !out.contains(need) && need != out.last) {
      out.add(need.clamp(0, last));
    } else if (!out.contains(last)) {
      out.add(last);
    }
  }
  return out;
}

/// Apply one window response: [okIndexes] gained src, [emptyIndexes] stayed empty.
FigureHydrateSnapshot applyWindowResult(
  FigureHydrateSnapshot prev, {
  required Set<int> previouslyFilled,
  required Set<int> newlyFilled,
  required Set<int> emptyIndexes,
  required Set<int> hardFailed,
}) {
  final filledSet = {...previouslyFilled, ...newlyFilled};
  final filled = filledSet.length;
  final failed = hardFailed.length;
  if (prev.total > 0 && filled >= prev.total && failed == 0) {
    return prev.copyWith(
      phase: FigureHydratePhase.doneOk,
      filled: filled,
      failed: 0,
    );
  }
  return prev.copyWith(
    phase: FigureHydratePhase.hydrating,
    filled: filled,
    failed: failed,
  );
}

FigureHydrateSnapshot finishHydrate(
  FigureHydrateSnapshot prev, {
  required int filled,
  required int failed,
}) {
  if (prev.total < 1) {
    return prev.copyWith(phase: FigureHydratePhase.doneOk, filled: 0, failed: 0);
  }
  if (failed < 1 && filled >= prev.total) {
    return prev.copyWith(
      phase: FigureHydratePhase.doneOk,
      filled: filled,
      failed: 0,
    );
  }
  if (failed < 1 && filled < prev.total) {
    // Still missing but no hard fail recorded → treat remaining as failed.
    final miss = prev.total - filled;
    return prev.copyWith(
      phase: FigureHydratePhase.donePartial,
      filled: filled,
      failed: miss,
    );
  }
  return prev.copyWith(
    phase: FigureHydratePhase.donePartial,
    filled: filled,
    failed: failed,
  );
}
