/// design/250 — merge helpers for focus + skill cloud sync (pure Dart).
library;

import 'dart:math' as math;

import 'focus_practice_models.dart';
import '../practice_skill/skill_history.dart';
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
  // design/509 — one device's own count only grows, so the larger wins
  // per device; different devices add up in [focusDaysWithDevices].
  final byDev = <String, Map<String, int>>{};
  for (final dev in {...a.byDev.keys, ...b.byDev.keys}) {
    final da = a.byDev[dev] ?? const <String, int>{};
    final db = b.byDev[dev] ?? const <String, int>{};
    final row = <String, int>{};
    for (final k in {...da.keys, ...db.keys}) {
      final m = math.max(da[k] ?? 0, db[k] ?? 0);
      if (m > 0) row[k] = m;
    }
    if (row.isNotEmpty) byDev[dev] = row;
  }
  final best = a.bestStreak > b.bestStreak ? a.bestStreak : b.bestStreak;
  final updated =
      a.updatedAtMs > b.updatedAtMs ? a.updatedAtMs : b.updatedAtMs;
  return FocusPracticeHistory(
    days: focusDaysWithDevices(days, byDev),
    bestStreak: best,
    sentencesRead: math.max(a.sentencesRead, b.sentencesRead),
    updatedAtMs: updated,
    byDev: byDev,
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
  final other = identical(live, b) ? a : b;
  // design/412 - a line only resets when its unit changes, so an empty one
  // beside a learned one is a copy that lost it on the way.
  final line = live.line.n == 0 && other.line.n > 0 ? other.line : live.line;
  return live.copyWith(
    days: days,
    updatedAtMs: updated,
    line: line,
    history: mergeSkillHistory(a.history, b.history),
    ladderFix: a.ladderFix > b.ladderFix ? a.ladderFix : b.ladderFix,
  );
}
