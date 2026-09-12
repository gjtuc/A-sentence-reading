/// design/250 — merge helpers for focus + skill cloud sync (pure Dart).
library;

import 'focus_practice_models.dart';
import '../practice_skill/skill_store.dart';

FocusPracticeHistory mergeFocusHistories(
  FocusPracticeHistory a,
  FocusPracticeHistory b,
) {
  final days = <String, int>{};
  for (final k in {...a.days.keys, ...b.days.keys}) {
    final na = a.days[k] ?? 0;
    final nb = b.days[k] ?? 0;
    final m = na > nb ? na : nb;
    if (m > 0) days[k] = m;
  }
  final best = a.bestStreak > b.bestStreak ? a.bestStreak : b.bestStreak;
  final updated =
      a.updatedAtMs > b.updatedAtMs ? a.updatedAtMs : b.updatedAtMs;
  return FocusPracticeHistory(
    days: days,
    bestStreak: best,
    updatedAtMs: updated,
  );
}

SkillState mergeSkillStates(SkillState a, SkillState b) {
  final live = b.updatedAtMs >= a.updatedAtMs ? b : a;
  final days = <String, SkillDayAgg>{};
  for (final k in {...a.days.keys, ...b.days.keys}) {
    final da = a.days[k];
    final db = b.days[k];
    if (da == null && db == null) continue;
    if (da == null) {
      days[k] = db!;
      continue;
    }
    if (db == null) {
      days[k] = da;
      continue;
    }
    if (db.n > da.n || (db.n == da.n && db.sum >= da.sum)) {
      days[k] = db;
    } else {
      days[k] = da;
    }
  }
  final updated =
      a.updatedAtMs > b.updatedAtMs ? a.updatedAtMs : b.updatedAtMs;
  return live.copyWith(days: days, updatedAtMs: updated);
}
