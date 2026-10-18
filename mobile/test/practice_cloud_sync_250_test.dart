/// design/250 — Dart merge helpers for focus + skill cloud sync.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/focus_practice_models.dart';
import 'package:sentence_reading/api/practice_cloud_merge.dart';
import 'package:sentence_reading/practice_skill/skill_store.dart';
import 'package:sentence_reading/practice_skill/pass_line.dart';
import 'package:sentence_reading/practice_skill/skill_history.dart';

void main() {
  test('mergeFocusHistories takes max blocks and streak', () {
    final a = FocusPracticeHistory(
      days: const {'2026-09-01': 1, '2026-09-02': 2},
      bestStreak: 1,
      updatedAtMs: 10,
    );
    final b = FocusPracticeHistory(
      days: const {'2026-09-01': 3},
      bestStreak: 4,
      updatedAtMs: 20,
    );
    final m = mergeFocusHistories(a, b);
    expect(m.days['2026-09-01'], 3);
    expect(m.days['2026-09-02'], 2);
    expect(m.bestStreak, 4);
    expect(m.updatedAtMs, 20);
  });

  test('mergeSkillStates days by n; live LWW by updatedAtMs', () {
    final a = SkillState(
      tier: 1,
      density: -1,
      updatedAtMs: 10,
      days: const {
        '2026-09-01': SkillDayAgg(sum: 4.0, n: 5),
      },
      epochTargetN: 6,
      epochMeans: const [0.8],
    );
    final b = SkillState(
      tier: 4,
      density: 1,
      updatedAtMs: 50,
      days: const {
        '2026-09-01': SkillDayAgg(sum: 1.9, n: 2),
      },
      epochTargetN: 8,
    );
    final m = mergeSkillStates(a, b);
    expect(m.days['2026-09-01']!.n, 5);
    expect(m.days['2026-09-01']!.sum, 4.0);
    expect(m.tier, 4);
    expect(m.density, 1);
    expect(m.epochTargetN, 8);
    expect(m.updatedAtMs, 50);
  });

  test('serialize round-trip includes updated_at_ms', () {
    final h = FocusPracticeHistory(
      days: const {'2026-09-01': 2},
      bestStreak: 2,
      updatedAtMs: 123,
    );
    final again = parseFocusPracticeHistory(serializeFocusPracticeHistory(h));
    expect(again.updatedAtMs, 123);
    expect(again.days['2026-09-01'], 2);
  });

  test('design/412 a reply that lost the line does not take it off the phone', () {
    // What the server sent back before design/412: no line, no pin.
    const reply = SkillState(tier: 3, density: 0, updatedAtMs: 50);
    const phone = SkillState(
      tier: 3,
      density: 0,
      updatedAtMs: 50,
      pinned: true,
      savedTier: 2,
      line: PassLine(avg: 0.7, varp: 0.02, n: 1300),
    );
    final m = mergeSkillStates(reply, phone);
    expect(m.line.n, 1300);
    expect(m.pinned, isTrue);
    expect(m.savedTier, 2);
  });

  test('design/412 history is the union and the fix mark only goes up', () {
    const one = SkillChange(
      atMs: 10,
      reason: 'hold',
      tierBefore: 2,
      densityBefore: 0,
      tier: 2,
      density: 0,
      avg: 0.9,
    );
    const two = SkillChange(
      atMs: 20,
      reason: 'reset',
      tierBefore: 3,
      densityBefore: 1,
      tier: 2,
      density: 0,
    );
    const a = SkillState(updatedAtMs: 30, history: [one], ladderFix: 0);
    const b = SkillState(updatedAtMs: 5, history: [one, two], ladderFix: 1);
    final m = mergeSkillStates(a, b);
    expect(m.history.map((c) => c.key).toList(), [one.key, two.key]);
    expect(m.ladderFix, 1);
    // A newer copy with an empty line keeps the learned one beside it.
    final lined = mergeSkillStates(
      const SkillState(updatedAtMs: 1, line: PassLine(avg: 0.7, n: 40)),
      const SkillState(updatedAtMs: 2),
    );
    expect(lined.line.n, 40);
  });
}
