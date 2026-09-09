import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/practice_grooming/grooming_policy.dart';

void main() {
  test('disabled never actuates', () {
    final p = GroomingPolicy(random: Random(1));
    final mem = GroomingMemory();
    final d = p.onOutcome(
      mem: mem,
      obs: const GroomingObservation(
        signal: GroomingSignal.takeFail,
        chunkKey: '0:0',
      ),
      enabled: false,
    );
    expect(d.applied, isFalse);
    expect(d.skipReason, 'disabled');
    expect(mem.pendingRateScale, isNull);
  });

  test('mic_perm observe only', () {
    final p = GroomingPolicy(random: Random(1));
    final mem = GroomingMemory();
    final d = p.onOutcome(
      mem: mem,
      obs: const GroomingObservation(
        signal: GroomingSignal.micPerm,
        chunkKey: '0:0',
      ),
      enabled: true,
    );
    expect(d.applied, isFalse);
    expect(d.skipReason, 'mic_perm_observe_only');
    expect(mem.pendingRateScale, isNull);
  });

  test('takeFail schedules rate nudge when roll applies', () {
    final p = GroomingPolicy(applyRoll: () => 0.0);
    final mem = GroomingMemory();
    p.beginCycle(mem);
    final d = p.onOutcome(
      mem: mem,
      obs: const GroomingObservation(
        signal: GroomingSignal.takeFail,
        chunkKey: '0:0',
      ),
      enabled: true,
    );
    expect(d.applied, isTrue);
    expect(d.action, GroomingActionKind.rateNudge);
    expect(mem.pendingRateScale, GroomingPolicy.rateScale);
    expect(p.beginCycle(mem), GroomingPolicy.rateScale);
    expect(p.beginCycle(mem), 1.0);
  });

  test('stochastic skip when roll high', () {
    final p = GroomingPolicy(applyRoll: () => 0.99);
    final mem = GroomingMemory();
    p.beginCycle(mem);
    final d = p.onOutcome(
      mem: mem,
      obs: const GroomingObservation(
        signal: GroomingSignal.takeFail,
        chunkKey: '0:0',
      ),
      enabled: true,
    );
    expect(d.applied, isFalse);
    expect(d.skipReason, 'stochastic_skip');
  });

  test('session cap blocks third intervention', () {
    final p = GroomingPolicy(applyRoll: () => 0.0);
    final mem = GroomingMemory();
    for (var i = 0; i < 2; i++) {
      p.beginCycle(mem);
      final d = p.onOutcome(
        mem: mem,
        obs: GroomingObservation(
          signal: GroomingSignal.takeTooShort,
          chunkKey: '0:$i',
        ),
        enabled: true,
      );
      expect(d.applied, isTrue);
      p.beginCycle(mem); // consume + advance seq away from rolling cap
      // Extra cycles so rolling window does not block before session cap.
      for (var j = 0; j < GroomingPolicy.rollingWindow; j++) {
        p.beginCycle(mem);
      }
    }
    p.beginCycle(mem);
    final blocked = p.onOutcome(
      mem: mem,
      obs: const GroomingObservation(
        signal: GroomingSignal.takeFail,
        chunkKey: '0:9',
      ),
      enabled: true,
    );
    expect(blocked.applied, isFalse);
    expect(blocked.skipReason, 'session_cap');
  });

  test('fade after clean streak', () {
    final p = GroomingPolicy(applyRoll: () => 0.0);
    final mem = GroomingMemory();
    for (var i = 0; i < GroomingPolicy.fadeCleanStreak; i++) {
      p.beginCycle(mem);
      p.onOutcome(
        mem: mem,
        obs: GroomingObservation(
          signal: GroomingSignal.clean,
          chunkKey: 'c:$i',
        ),
        enabled: true,
      );
    }
    expect(mem.suppressRemaining, GroomingPolicy.fadeSuppressChunks);
    p.beginCycle(mem);
    final d = p.onOutcome(
      mem: mem,
      obs: const GroomingObservation(
        signal: GroomingSignal.takeFail,
        chunkKey: 'x',
      ),
      enabled: true,
    );
    expect(d.applied, isFalse);
    expect(d.skipReason, 'fade_suppress');
  });

  test('resetSession clears pending', () {
    final p = GroomingPolicy(applyRoll: () => 0.0);
    final mem = GroomingMemory();
    p.beginCycle(mem);
    p.onOutcome(
      mem: mem,
      obs: const GroomingObservation(
        signal: GroomingSignal.takeFail,
        chunkKey: '0:0',
      ),
      enabled: true,
    );
    expect(mem.pendingRateScale, isNotNull);
    p.resetSession(mem);
    expect(mem.pendingRateScale, isNull);
    expect(mem.interventionsThisSession, 0);
    expect(p.beginCycle(mem), 1.0);
  });
}
