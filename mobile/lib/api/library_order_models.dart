/// Library paper order prefs (design/101).
///
/// WHY pure Dart: unit-test without SharedPreferences.
/// EDGE: missing/garbage → empty order (server/default list order).
library;

const String kLibraryOrderPrefsKeyBase = 'asr.library.order.v1';

String libraryOrderPrefsKey(String? uid) {
  final u = (uid ?? '').trim();
  if (u.isEmpty) return kLibraryOrderPrefsKeyBase;
  return '$kLibraryOrderPrefsKeyBase.$u';
}

/// Parse JSON `{"ids":["a","b"]}` or legacy comma-separated ids.
List<String> parseLibraryOrderPref(String? raw) {
  final s = (raw ?? '').trim();
  if (s.isEmpty) return const [];
  if (s.startsWith('{')) {
    final m = RegExp(r'"ids"\s*:\s*\[(.*?)\]', dotAll: true).firstMatch(s);
    if (m == null) return const [];
    final inner = m.group(1) ?? '';
    final ids = <String>[];
    for (final hit in RegExp(r'"([^"]+)"').allMatches(inner)) {
      final id = (hit.group(1) ?? '').trim();
      if (id.isNotEmpty) ids.add(id);
    }
    return ids;
  }
  // legacy: id1,id2
  return s
      .split(',')
      .map((e) => e.trim())
      .where((e) => e.isNotEmpty)
      .toList(growable: false);
}

String serializeLibraryOrderPref(List<String> ids) {
  final cleaned = ids
      .map((e) => e.trim())
      .where((e) => e.isNotEmpty)
      .toList(growable: false);
  final body = cleaned.map((e) => '"$e"').join(',');
  return '{"ids":[$body]}';
}

/// Apply saved [orderIds] onto [papers]. Unknown saved ids dropped.
/// Papers not in [orderIds] keep relative server order and appear **first**.
List<T> applyLibraryOrder<T>({
  required List<T> papers,
  required List<String> orderIds,
  required String Function(T) idOf,
}) {
  if (papers.isEmpty) return papers;
  if (orderIds.isEmpty) return papers;
  final byId = <String, T>{};
  for (final p in papers) {
    final id = idOf(p).trim();
    if (id.isEmpty) continue;
    byId[id] = p;
  }
  final ordered = <T>[];
  final seen = <String>{};
  for (final id in orderIds) {
    final p = byId[id];
    if (p == null) continue;
    if (!seen.add(id)) continue;
    ordered.add(p);
  }
  final fresh = <T>[];
  for (final p in papers) {
    final id = idOf(p).trim();
    if (id.isEmpty || seen.contains(id)) continue;
    fresh.add(p);
  }
  return [...fresh, ...ordered];
}
