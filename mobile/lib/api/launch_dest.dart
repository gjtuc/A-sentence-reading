/// design/313 — app start surface. Default is the library.
library;

import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import 'practice_progress_store.dart';
import 'progress_gate.dart';

enum LaunchDest { library, practice, read }

const String kLaunchDestPrefsKeyBase = 'asr.launch_dest.v1';

String launchDestPrefsKey(String? uid) {
  final u = (uid ?? '').trim();
  if (u.isEmpty) return kLaunchDestPrefsKeyBase;
  final safe = u.length > 128 ? u.substring(0, 128) : u;
  return '$kLaunchDestPrefsKeyBase.u.$safe';
}

LaunchDest launchDestFromStored(String? raw) {
  switch ((raw ?? '').trim()) {
    case 'practice':
      return LaunchDest.practice;
    case 'read':
      return LaunchDest.read;
    default:
      return LaunchDest.library;
  }
}

String launchDestStored(LaunchDest dest) {
  switch (dest) {
    case LaunchDest.practice:
      return 'practice';
    case LaunchDest.read:
      return 'read';
    case LaunchDest.library:
      return 'library';
  }
}

Future<LaunchDest> loadLaunchDest(String? uid) async {
  final p = await SharedPreferences.getInstance();
  return launchDestFromStored(p.getString(launchDestPrefsKey(uid)));
}

Future<void> saveLaunchDest(String? uid, LaunchDest dest) async {
  final p = await SharedPreferences.getInstance();
  await p.setString(launchDestPrefsKey(uid), launchDestStored(dest));
}

/// Latest `at` among [liveIds]. Missing or deleted ids are ignored.
String? latestLiveCacheId(Map<String, String> atById, Set<String> liveIds) {
  String? best;
  var bestAt = '';
  for (final e in atById.entries) {
    if (!liveIds.contains(e.key)) continue;
    if (e.value.compareTo(bestAt) > 0) {
      bestAt = e.value;
      best = e.key;
    }
  }
  return best;
}

class LaunchOpen {
  const LaunchOpen({required this.cacheId, required this.practice});

  final String cacheId;
  final bool practice;
}

/// Next-process start surface. Null stays on the library.
LaunchOpen? resolveLaunchOpen({
  required LaunchDest dest,
  required bool shadowingOn,
  required Map<String, String> readAt,
  required Map<String, String> practiceAt,
  required Set<String> liveIds,
}) {
  if (dest == LaunchDest.library) return null;
  if (dest == LaunchDest.practice) {
    if (!shadowingOn) return null;
    final id = latestLiveCacheId(practiceAt, liveIds);
    if (id == null || id.isEmpty) return null;
    return LaunchOpen(cacheId: id, practice: true);
  }
  final id = latestLiveCacheId(readAt, liveIds);
  if (id == null || id.isEmpty) return null;
  return LaunchOpen(cacheId: id, practice: false);
}

Map<String, String> atByCacheIdFromStore(Object? papers) {
  if (papers is! Map) return const {};
  final out = <String, String>{};
  for (final e in papers.entries) {
    final key = '${e.key}';
    if (!key.startsWith('cache:')) continue;
    final id = key.substring('cache:'.length).trim();
    if (id.isEmpty || e.value is! Map) continue;
    final at = '${(e.value as Map)['at'] ?? ''}'.trim();
    if (at.isEmpty) continue;
    out[id] = at;
  }
  return out;
}

Future<Map<String, String>> loadReadAtByCacheId(String? uid) async {
  return _loadAt(progressPrefsKey(uid));
}

Future<Map<String, String>> loadPracticeAtByCacheId(String? uid) async {
  return _loadAt(practiceProgressPrefsKey(uid));
}

Future<Map<String, String>> _loadAt(String key) async {
  final p = await SharedPreferences.getInstance();
  final raw = p.getString(key);
  if (raw == null || raw.isEmpty) return const {};
  try {
    final map = jsonDecode(raw);
    if (map is! Map || map['version'] != 1) return const {};
    return atByCacheIdFromStore(map['papers']);
  } catch (_) {
    return const {};
  }
}
