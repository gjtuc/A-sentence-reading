/// design/176 — focus practice (10‑min speaking blocks · daily success).
///
/// Pure Dart: unit-test without Flutter bindings.
library;

import 'dart:convert';

/// Production block length. Tests inject a shorter [FocusPracticeController.blockDuration].
const Duration kFocusPracticeBlockDuration = Duration(minutes: 10);

const String kFocusPracticePrefsKeyBase = 'asr.focus_practice.v1';

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

FocusPracticeDayState parseFocusPracticeDayState(String? raw) {
  final s = (raw ?? '').trim();
  if (s.isEmpty || !s.startsWith('{')) {
    return FocusPracticeDayState(day: focusPracticeDayKey());
  }
  try {
    final decoded = jsonDecode(s);
    if (decoded is! Map) {
      return FocusPracticeDayState(day: focusPracticeDayKey());
    }
    final day = '${decoded['day'] ?? ''}'.trim();
    final today = focusPracticeDayKey();
    if (day.isEmpty || day != today) {
      return FocusPracticeDayState(day: today);
    }
    final blocks = decoded['blocks_completed'];
    final n = blocks is int
        ? blocks
        : int.tryParse('$blocks') ?? 0;
    final success = decoded['success'] == true || n > 0;
    return FocusPracticeDayState(
      day: day,
      success: success,
      blocksCompleted: n < 0 ? 0 : n,
    );
  } catch (_) {
    return FocusPracticeDayState(day: focusPracticeDayKey());
  }
}

String serializeFocusPracticeDayState(FocusPracticeDayState s) {
  return jsonEncode({
    'day': s.day,
    'success': s.success,
    'blocks_completed': s.blocksCompleted,
  });
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
