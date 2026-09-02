import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/state/harmonize_residual.dart';

void main() {
  test('userLabel running fraction', () {
    const s = HarmonizeResidualSnapshot(
      cacheId: 'abc',
      phase: HarmonizeResidualPhase.running,
      total: 120,
      done: 40,
      failed: 0,
    );
    expect(s.userLabel, '재감수 40/120 중');
    expect(s.showProgress, isTrue);
  });

  test('userLabel hides when doneOk', () {
    const s = HarmonizeResidualSnapshot(
      cacheId: 'abc',
      phase: HarmonizeResidualPhase.doneOk,
      total: 10,
      done: 10,
      failed: 0,
    );
    expect(s.hideBanner, isTrue);
    expect(s.userLabel, isEmpty);
  });

  test('snapshotFromServerFields pending', () {
    final s = snapshotFromServerFields(
      cacheId: 'x',
      pending: true,
      total: 10,
      done: 3,
      failed: 0,
    );
    expect(s.phase, HarmonizeResidualPhase.running);
    expect(s.userLabel, '재감수 3/10 중');
  });

  test('snapshotFromServerFields partial', () {
    final s = snapshotFromServerFields(
      cacheId: 'x',
      pending: false,
      total: 10,
      done: 8,
      failed: 2,
    );
    expect(s.phase, HarmonizeResidualPhase.donePartial);
    expect(s.userLabel, '재감수 2문장 실패');
  });
}
