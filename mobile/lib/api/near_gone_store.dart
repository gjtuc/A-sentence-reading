/// design/450 — papers the user deleted, so near sync can spread the delete.
library;

import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

const int kNearGoneKeep = 2000;

String nearGonePrefsKey(String uid) => 'near_gone_v1_$uid';

Map<String, int> nearGoneDecode(String? raw) {
  if (raw == null || raw.isEmpty) return {};
  try {
    final m = jsonDecode(raw);
    if (m is! Map) return {};
    final out = <String, int>{};
    for (final e in m.entries) {
      final v = e.value;
      if (v is int && v > 0 && '${e.key}'.isNotEmpty) out['${e.key}'] = v;
    }
    return out;
  } catch (_) {
    return {};
  }
}

/// [base] plus [more], newest time per id, the newest [kNearGoneKeep] kept.
Map<String, int> nearGoneMerge(Map<String, int> base, Map<String, int> more) {
  final out = Map<String, int>.from(base);
  for (final e in more.entries) {
    final id = e.key.trim();
    if (id.isEmpty || e.value <= 0) continue;
    final had = out[id];
    if (had == null || e.value > had) out[id] = e.value;
  }
  if (out.length <= kNearGoneKeep) return out;
  final rows = out.entries.toList()..sort((a, b) => b.value.compareTo(a.value));
  return {for (final e in rows.take(kNearGoneKeep)) e.key: e.value};
}

Future<Map<String, int>> loadNearGone(String? uid, {SharedPreferences? prefs}) async {
  final u = (uid ?? '').trim();
  if (u.isEmpty) return {};
  final p = prefs ?? await SharedPreferences.getInstance();
  return nearGoneDecode(p.getString(nearGonePrefsKey(u)));
}

Future<void> addNearGone(
  String? uid,
  Map<String, int> more, {
  SharedPreferences? prefs,
}) async {
  final u = (uid ?? '').trim();
  if (u.isEmpty || more.isEmpty) return;
  final p = prefs ?? await SharedPreferences.getInstance();
  final next = nearGoneMerge(nearGoneDecode(p.getString(nearGonePrefsKey(u))), more);
  await p.setString(nearGonePrefsKey(u), jsonEncode(next));
}
