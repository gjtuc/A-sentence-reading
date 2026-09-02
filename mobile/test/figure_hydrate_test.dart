import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/state/figure_hydrate.dart';

void main() {
  test('userLabel hides when doneOk', () {
    const s = FigureHydrateSnapshot(
      cacheId: 'abc',
      phase: FigureHydratePhase.doneOk,
      total: 14,
      filled: 14,
      failed: 0,
    );
    expect(s.hideBanner, isTrue);
    expect(s.userLabel, isEmpty);
  });

  test('userLabel hydrating is honest fraction', () {
    const s = FigureHydrateSnapshot(
      cacheId: 'abc',
      phase: FigureHydratePhase.hydrating,
      total: 14,
      filled: 5,
      failed: 0,
    );
    expect(s.userLabel, '그림 5/14 받는 중');
    expect(s.showProgress, isTrue);
  });

  test('userLabel partial failure', () {
    const s = FigureHydrateSnapshot(
      cacheId: 'abc',
      phase: FigureHydratePhase.donePartial,
      total: 14,
      filled: 12,
      failed: 2,
    );
    expect(s.userLabel, '그림 2장 받지 못함');
    expect(s.showFailure, isTrue);
  });

  test('hydrateCenters span=1 covers all indices', () {
    final centers = hydrateCenters(total: 14, span: 1);
    final covered = <int>{};
    for (final c in centers) {
      for (var i = c - 1; i <= c + 1; i++) {
        if (i >= 0 && i < 14) covered.add(i);
      }
    }
    expect(covered.length, 14);
  });

  test('finishHydrate partial when gaps remain', () {
    const prev = FigureHydrateSnapshot(
      cacheId: 'abc',
      phase: FigureHydratePhase.hydrating,
      total: 10,
      filled: 8,
      failed: 0,
    );
    final done = finishHydrate(prev, filled: 8, failed: 0);
    expect(done.phase, FigureHydratePhase.donePartial);
    expect(done.failed, 2);
  });

  test('countFilledFromSrcList', () {
    expect(countFilledFromSrcList(['a', '', 'b', '  ']), 2);
  });
}
