/// design/250 — Dart merge helpers for focus + skill cloud sync.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/focus_practice_models.dart';
import 'package:sentence_reading/api/practice_cloud_merge.dart';
import 'package:sentence_reading/practice_skill/skill_store.dart';

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
}
