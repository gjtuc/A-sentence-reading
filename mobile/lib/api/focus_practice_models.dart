/// design/176 + calendar streak — 10‑min speaking blocks · daily history.
///
/// Pure Dart: unit-test without Flutter bindings.
library;

import 'dart:convert';
import 'dart:math' as math;

/// Production block length. Tests inject a shorter [FocusPracticeController.blockDuration].
const Duration kFocusPracticeBlockDuration = Duration(minutes: 10);

const String kFocusPracticePrefsKeyBase = 'asr.focus_practice.v1';

/// Streak milestone days shown as soft “참 잘했어요” chips.
const List<int> kFocusStreakMilestones = [3, 7, 10, 14];

String focusPracticePrefsKey(String? uid) {
  final u = (uid ?? '').trim();
  if (u.isEmpty) return kFocusPracticePrefsKeyBase;
  return '$kFocusPracticePrefsKeyBase.$u';
}

/// Local calendar day `yyyy-MM-dd` (device timezone).
String focusPracticeDayKey([DateTime? now]) {
  final n = now ?? DateTime.now();
  final local = n.isUtc ? n.toLocal() : n;
  final y = local.year.toString().padLeft(4, '0');
  final m = local.month.toString().padLeft(2, '0');
  final d = local.day.toString().padLeft(2, '0');
  return '$y-$m-$d';
}

DateTime? parseFocusPracticeDayKey(String key) {
  final t = key.trim();
  if (!RegExp(r'^\d{4}-\d{2}-\d{2}$').hasMatch(t)) return null;
  final y = int.tryParse(t.substring(0, 4));
  final m = int.tryParse(t.substring(5, 7));
  final d = int.tryParse(t.substring(8, 10));
  if (y == null || m == null || d == null) return null;
  return DateTime(y, m, d);
}

String focusPracticeAddDays(String dayKey, int deltaDays) {
  final base = parseFocusPracticeDayKey(dayKey);
  if (base == null) return dayKey;
  return focusPracticeDayKey(base.add(Duration(days: deltaDays)));
}

class FocusPracticeDayState {
  const FocusPracticeDayState({
    this.day = '',
    this.success = false,
    this.blocksCompleted = 0,
  });

  final String day;
  final bool success;
  final int blocksCompleted;

  FocusPracticeDayState copyWith({
    String? day,
    bool? success,
    int? blocksCompleted,
  }) {
    return FocusPracticeDayState(
      day: day ?? this.day,
      success: success ?? this.success,
      blocksCompleted: blocksCompleted ?? this.blocksCompleted,
    );
  }
}

/// Multi-day local history (v2). Survives day rollover.
class FocusPracticeHistory {
  const FocusPracticeHistory({
    this.version = 2,
    this.days = const {},
    this.bestStreak = 0,
  });

  final int version;
  /// day key → blocks completed that day.
  final Map<String, int> days;
  final int bestStreak;

  FocusPracticeHistory copyWith({
    Map<String, int>? days,
    int? bestStreak,
  }) {
    return FocusPracticeHistory(
      version: version,
      days: days ?? this.days,
      bestStreak: bestStreak ?? this.bestStreak,
    );
  }

  int blocksFor(String dayKey) => days[dayKey] ?? 0;

  FocusPracticeDayState dayStateFor(String dayKey) {
    final n = blocksFor(dayKey);
    return FocusPracticeDayState(
      day: dayKey,
      success: n > 0,
      blocksCompleted: n,
    );
  }
}

FocusPracticeHistory emptyFocusPracticeHistory([String? today]) {
  return const FocusPracticeHistory();
}

FocusPracticeHistory parseFocusPracticeHistory(String? raw) {
  final s = (raw ?? '').trim();
  if (s.isEmpty || !s.startsWith('{')) {
    return const FocusPracticeHistory();
  }
  try {
    final decoded = jsonDecode(s);
    if (decoded is! Map) return const FocusPracticeHistory();

    // v2: { version, days: { yyyy-MM-dd: n }, best_streak }
    if (decoded['days'] is Map || decoded['version'] == 2) {
      final daysRaw = decoded['days'];
      final days = <String, int>{};
      if (daysRaw is Map) {
        for (final e in daysRaw.entries) {
          final k = '${e.key}'.trim();
          if (parseFocusPracticeDayKey(k) == null) continue;
          final v = e.value;
          final n = v is int ? v : int.tryParse('$v') ?? 0;
          if (n > 0) days[k] = n;
        }
      }
      final bestRaw = decoded['best_streak'];
      var best = bestRaw is int ? bestRaw : int.tryParse('$bestRaw') ?? 0;
      if (best < 0) best = 0;
      final computed = computeFocusBestStreak(days);
      if (computed > best) best = computed;
      return FocusPracticeHistory(days: days, bestStreak: best);
    }

    // v1 migrate: single { day, success, blocks_completed }
    final day = '${decoded['day'] ?? ''}'.trim();
    final blocks = decoded['blocks_completed'];
    final n = blocks is int ? blocks : int.tryParse('$blocks') ?? 0;
    final success = decoded['success'] == true || n > 0;
    if (day.isEmpty || parseFocusPracticeDayKey(day) == null || !success || n <= 0) {
      return const FocusPracticeHistory();
    }
    return FocusPracticeHistory(
      days: {day: n},
      bestStreak: 1,
    );
  } catch (_) {
    return const FocusPracticeHistory();
  }
}

String serializeFocusPracticeHistory(FocusPracticeHistory h) {
  final days = <String, int>{
    for (final e in h.days.entries)
      if (e.value > 0) e.key: e.value,
  };
  return jsonEncode({
    'version': 2,
    'days': days,
    'best_streak': h.bestStreak < 0 ? 0 : h.bestStreak,
  });
}

/// Backward-compatible aliases used by older tests / call sites.
FocusPracticeDayState parseFocusPracticeDayState(String? raw) {
  final today = focusPracticeDayKey();
  final hist = parseFocusPracticeHistory(raw);
  return hist.dayStateFor(today);
}

String serializeFocusPracticeDayState(FocusPracticeDayState s) {
  // Prefer writing v2 with at least today's entry.
  final days = <String, int>{};
  if (s.blocksCompleted > 0 && s.day.isNotEmpty) {
    days[s.day] = s.blocksCompleted;
  }
  return serializeFocusPracticeHistory(
    FocusPracticeHistory(
      days: days,
      bestStreak: s.blocksCompleted > 0 ? 1 : 0,
    ),
  );
}

/// Current streak: consecutive days with ≥1 block.
///
/// If today has blocks, ends today; else if yesterday has blocks, ends yesterday
/// (streak still “alive” until the day ends). Otherwise 0.
int computeFocusCurrentStreak(
  Map<String, int> days, {
  required String todayKey,
}) {
  String tip = todayKey;
  if ((days[todayKey] ?? 0) <= 0) {
    final y = focusPracticeAddDays(todayKey, -1);
    if ((days[y] ?? 0) <= 0) return 0;
    tip = y;
  }
  var n = 0;
  var cursor = tip;
  while ((days[cursor] ?? 0) > 0) {
    n += 1;
    cursor = focusPracticeAddDays(cursor, -1);
    if (n > 4000) break;
  }
  return n;
}

int computeFocusBestStreak(Map<String, int> days) {
  if (days.isEmpty) return 0;
  final keys = days.keys.where((k) => (days[k] ?? 0) > 0).toList()..sort();
  if (keys.isEmpty) return 0;
  var best = 1;
  var run = 1;
  for (var i = 1; i < keys.length; i++) {
    final prev = parseFocusPracticeDayKey(keys[i - 1]);
    final cur = parseFocusPracticeDayKey(keys[i]);
    if (prev != null &&
        cur != null &&
        cur.difference(prev).inDays == 1) {
      run += 1;
      if (run > best) best = run;
    } else {
      run = 1;
    }
  }
  return best;
}

/// Heatmap intensity 0..3 from blocks that day (single palette).
int focusHeatLevel(int blocks) {
  if (blocks <= 0) return 0;
  if (blocks == 1) return 1;
  if (blocks == 2) return 2;
  return 3;
}

/// Highest milestone reached by [streak] (or null).
int? focusStreakMilestoneReached(int streak) {
  int? hit;
  for (final m in kFocusStreakMilestones) {
    if (streak >= m) hit = m;
  }
  return hit;
}

List<int> focusStreakMilestonesHit(int streak) {
  return [
    for (final m in kFocusStreakMilestones)
      if (streak >= m) m,
  ];
}

String formatFocusClock(Duration d) {
  final total = d.inSeconds;
  final safe = total < 0 ? 0 : total;
  final h = safe ~/ 3600;
  final m = (safe % 3600) ~/ 60;
  final sec = safe % 60;
  String two(int n) => n.toString().padLeft(2, '0');
  if (h > 0) return '${two(h)}:${two(m)}:${two(sec)}';
  return '${two(m)}:${two(sec)}';
}

/// Days in a month grid (Sun-start), including leading/trailing padding nulls.
List<String?> focusMonthCellKeys(int year, int month) {
  final first = DateTime(year, month, 1);
  final daysInMonth = DateTime(year, month + 1, 0).day;
  final lead = first.weekday % 7; // Sun=0
  final cells = <String?>[];
  for (var i = 0; i < lead; i++) {
    cells.add(null);
  }
  for (var d = 1; d <= daysInMonth; d++) {
    cells.add(focusPracticeDayKey(DateTime(year, month, d)));
  }
  while (cells.length % 7 != 0) {
    cells.add(null);
  }
  return cells;
}

/// Clamp helper for UI.
int clampFocusBlocks(int n) => math.max(0, n);
