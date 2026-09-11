/// Soft-delete pending entries (design/224).
library;

import 'dart:convert';

const String kSoftDeletePrefsPrefix = 'asr.lib_soft_del.v1.u.';
const Duration kSoftDeleteGrace = Duration(seconds: 60);

String softDeletePrefsKey(String uid) {
  final safe = uid.trim().replaceAll(RegExp(r'[^a-zA-Z0-9_-]'), '_');
  if (safe.isEmpty) return '${kSoftDeletePrefsPrefix}anon';
  return '$kSoftDeletePrefsPrefix$safe';
}

class SoftDeleteEntry {
  SoftDeleteEntry({
    required this.cacheId,
    required this.purgeAtMs,
  });

  final String cacheId;
  final int purgeAtMs;

  Map<String, dynamic> toJson() => {
        'cache_id': cacheId,
        'purge_at_ms': purgeAtMs,
      };

  static SoftDeleteEntry? fromJson(Map<String, dynamic> m) {
    final id = '${m['cache_id'] ?? m['cacheId'] ?? ''}'.trim();
    final raw = m['purge_at_ms'] ?? m['purgeAtMs'];
    final purgeAt = raw is num
        ? raw.toInt()
        : int.tryParse('${raw ?? ''}') ?? 0;
    if (id.isEmpty || purgeAt <= 0) return null;
    return SoftDeleteEntry(cacheId: id, purgeAtMs: purgeAt);
  }
}

class SoftDeleteList {
  SoftDeleteList({List<SoftDeleteEntry>? entries})
      : entries = List<SoftDeleteEntry>.unmodifiable(entries ?? const []);

  final List<SoftDeleteEntry> entries;

  bool get isEmpty => entries.isEmpty;

  Set<String> get hiddenIds =>
      {for (final e in entries) e.cacheId};

  int? get earliestPurgeAtMs {
    if (entries.isEmpty) return null;
    var min = entries.first.purgeAtMs;
    for (final e in entries) {
      if (e.purgeAtMs < min) min = e.purgeAtMs;
    }
    return min;
  }

  List<SoftDeleteEntry> dueAt(int nowMs) =>
      entries.where((e) => e.purgeAtMs <= nowMs).toList(growable: false);

  String encode() => jsonEncode({
        'v': 1,
        'entries': entries.map((e) => e.toJson()).toList(),
      });

  static SoftDeleteList tryParse(String? raw) {
    if (raw == null || raw.trim().isEmpty) return SoftDeleteList();
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map) return SoftDeleteList();
      final list = decoded['entries'];
      if (list is! List) return SoftDeleteList();
      final out = <SoftDeleteEntry>[];
      final seen = <String>{};
      for (final row in list) {
        if (row is! Map) continue;
        final item =
            SoftDeleteEntry.fromJson(Map<String, dynamic>.from(row));
        if (item == null) continue;
        if (!seen.add(item.cacheId)) continue;
        out.add(item);
      }
      return SoftDeleteList(entries: out);
    } catch (_) {
      return SoftDeleteList();
    }
  }
}
