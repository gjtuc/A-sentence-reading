/// design/123 — durable uid-scoped reading progress (sentence+figure).
library;

import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import 'progress_gate.dart';

/// Raw stored indices (may be non-int — validateProgressIndices decides).
class StoredProgressRaw {
  const StoredProgressRaw({
    required this.sentenceIndex,
    required this.figureIndex,
    this.layoutMode = '',
    this.sectionLabel = '',
  });

  final Object? sentenceIndex;
  final Object? figureIndex;
  final String layoutMode;
  final String sectionLabel;
}

String progressCacheKey(String cacheId) => 'cache:${cacheId.trim()}';

/// Load raw row for [cacheId] (null = no stored progress / unusable store).
Future<StoredProgressRaw?> loadProgressRaw({
  required String? uid,
  required String cacheId,
}) async {
  final cid = cacheId.trim();
  if (cid.isEmpty) return null;
  final p = await SharedPreferences.getInstance();
  final raw = p.getString(progressPrefsKey(uid));
  if (raw == null || raw.isEmpty) return null;
  try {
    final map = jsonDecode(raw);
    if (map is! Map) return null;
    final papers = map['papers'];
    if (papers is! Map) return null;
    final row = papers[progressCacheKey(cid)];
    if (row is! Map) return null;
    if (!row.containsKey('sentence_index') || !row.containsKey('figure_index')) {
      return null;
    }
    return StoredProgressRaw(
      sentenceIndex: row['sentence_index'],
      figureIndex: row['figure_index'],
      layoutMode: '${row['layout_mode'] ?? ''}'.trim(),
      sectionLabel: '${row['section_label'] ?? ''}'.trim(),
    );
  } catch (_) {
    // EDGE: corrupt JSON → no progress (open at default).
    return null;
  }
}

/// Persist both indices. Caller saves in-memory cursors (already valid).
///
/// design/411 — `at` is when the spot was reached: a save at the same spot keeps
/// it, and a spot taken from another device passes that device's [at].
Future<void> saveProgressRow({
  required String? uid,
  required String cacheId,
  required int sentenceIndex,
  required int figureIndex,
  String layoutMode = '',
  String sectionLabel = '',
  String? at,
}) async {
  final cid = cacheId.trim();
  if (cid.isEmpty) return;
  final p = await SharedPreferences.getInstance();
  final key = progressPrefsKey(uid);
  Map<String, dynamic> store = {'version': 1, 'papers': <String, dynamic>{}};
  final raw = p.getString(key);
  if (raw != null && raw.isNotEmpty) {
    try {
      final decoded = jsonDecode(raw);
      if (decoded is Map && decoded['version'] == 1) {
        store = Map<String, dynamic>.from(decoded);
        final papers = store['papers'];
        store['papers'] = papers is Map
            ? Map<String, dynamic>.from(papers)
            : <String, dynamic>{};
      }
    } catch (_) {
      // overwrite corrupt store
    }
  }
  final papers = Map<String, dynamic>.from(
    (store['papers'] as Map?) ?? <String, dynamic>{},
  );
  final prev = papers[progressCacheKey(cid)];
  final sameSpot = prev is Map &&
      prev['sentence_index'] == sentenceIndex &&
      prev['figure_index'] == figureIndex &&
      prev['at'] is String &&
      (prev['at'] as String).isNotEmpty;
  papers[progressCacheKey(cid)] = {
    'sentence_index': sentenceIndex,
    'figure_index': figureIndex,
    if (layoutMode.trim().isNotEmpty) 'layout_mode': layoutMode.trim(),
    if (sectionLabel.trim().isNotEmpty) 'section_label': sectionLabel.trim(),
    'at': at ??
        (sameSpot ? prev['at'] as String : DateTime.now().toUtc().toIso8601String()),
  };
  if (papers.length > 500) {
    final entries = papers.entries.toList()
      ..sort((a, b) {
        final atA = '${(a.value is Map) ? a.value['at'] : ''}';
        final atB = '${(b.value is Map) ? b.value['at'] : ''}';
        return atA.compareTo(atB);
      });
    final drop = papers.length - 500;
    for (var i = 0; i < drop; i++) {
      papers.remove(entries[i].key);
    }
  }
  store['papers'] = papers;
  store['version'] = 1;
  await p.setString(key, jsonEncode(store));
}

/// design/160 — when user leaves reading tab / backgrounds app.
Future<void> recordReadLeftAt({
  required String? uid,
  required String cacheId,
}) async {
  final cid = cacheId.trim();
  if (cid.isEmpty) return;
  final p = await SharedPreferences.getInstance();
  final prefsKey = progressPrefsKey(uid);
  Map<String, dynamic> store = {'version': 1, 'papers': <String, dynamic>{}};
  final raw = p.getString(prefsKey);
  if (raw != null && raw.isNotEmpty) {
    try {
      final decoded = jsonDecode(raw);
      if (decoded is Map && decoded['version'] == 1) {
        store = Map<String, dynamic>.from(decoded);
        final papers = store['papers'];
        store['papers'] = papers is Map
            ? Map<String, dynamic>.from(papers)
            : <String, dynamic>{};
      }
    } catch (_) {
      // overwrite corrupt store
    }
  }
  final papers = Map<String, dynamic>.from(
    (store['papers'] as Map?) ?? <String, dynamic>{},
  );
  final rowKey = progressCacheKey(cid);
  final row = Map<String, dynamic>.from(
    (papers[rowKey] is Map) ? papers[rowKey] as Map : <String, dynamic>{},
  );
  row['last_read_left_at'] = DateTime.now().toUtc().toIso8601String();
  papers[rowKey] = row;
  store['papers'] = papers;
  store['version'] = 1;
  await p.setString(prefsKey, jsonEncode(store));
}

/// Load stored read-left timestamp for one paper (ISO UTC).
Future<String?> loadLastReadLeftAt({
  required String? uid,
  required String cacheId,
}) async {
  final cid = cacheId.trim();
  if (cid.isEmpty) return null;
  final p = await SharedPreferences.getInstance();
  final raw = p.getString(progressPrefsKey(uid));
  if (raw == null || raw.isEmpty) return null;
  try {
    final map = jsonDecode(raw);
    if (map is! Map) return null;
    final papers = map['papers'];
    if (papers is! Map) return null;
    final row = papers[progressCacheKey(cid)];
    if (row is! Map) return null;
    final at = row['last_read_left_at'];
    if (at is! String || at.trim().isEmpty) return null;
    return at.trim();
  } catch (_) {
    return null;
  }
}

/// Batch load read-left times for library rows.
Future<Map<String, String>> loadReadLeftAtForPapers({
  required String? uid,
  required Iterable<String> cacheIds,
}) async {
  final out = <String, String>{};
  for (final id in cacheIds) {
    final cid = id.trim();
    if (cid.isEmpty) continue;
    final at = await loadLastReadLeftAt(uid: uid, cacheId: cid);
    if (at != null) out[cid] = at;
  }
  return out;
}


/// Library subtitles from stored progress rows (sentence/figure/section).
Future<Map<String, String>> loadProgressResumeLabels({
  required String? uid,
  required Iterable<String> cacheIds,
}) async {
  final out = <String, String>{};
  final want = {for (final id in cacheIds) id.trim()}.difference({''});
  if (want.isEmpty) return out;
  final p = await SharedPreferences.getInstance();
  final raw = p.getString(progressPrefsKey(uid));
  if (raw == null || raw.isEmpty) return out;
  try {
    final map = jsonDecode(raw);
    if (map is! Map) return out;
    final papers = map['papers'];
    if (papers is! Map) return out;
    for (final cid in want) {
      final row = papers[progressCacheKey(cid)];
      if (row is! Map) continue;
      final si = row['sentence_index'];
      final fi = row['figure_index'];
      if (si is! num || fi is! num) continue;
      final section = (row["section_label"]?.toString() ?? "").trim();
      // design/196 — section only; library composes totals + section + reading mark.
      out[cid] = section;
    }
  } catch (_) {
    return out;
  }
  return out;
}

/// design/410 — every stored row, keyed by cache id (for near sync).
Future<Map<String, Map<String, dynamic>>> loadProgressRows({
  required String? uid,
}) async {
  final out = <String, Map<String, dynamic>>{};
  final p = await SharedPreferences.getInstance();
  final raw = p.getString(progressPrefsKey(uid));
  if (raw == null || raw.isEmpty) return out;
  try {
    final map = jsonDecode(raw);
    if (map is! Map || map['papers'] is! Map) return out;
    for (final e in (map['papers'] as Map).entries) {
      final key = '${e.key}';
      if (!key.startsWith('cache:') || e.value is! Map) continue;
      final cid = key.substring('cache:'.length).trim();
      if (cid.isEmpty) continue;
      out[cid] = Map<String, dynamic>.from(e.value as Map);
    }
  } catch (_) {
    return out;
  }
  return out;
}

/// design/410 — fold another device's rows into this one.
///
/// The newer `at` wins the reading spot; `last_read_left_at` keeps the later time.
/// Returns how many rows changed.
Future<int> mergeProgressRows({
  required String? uid,
  required Map<String, Map<String, dynamic>> incoming,
}) async {
  if (incoming.isEmpty) return 0;
  final p = await SharedPreferences.getInstance();
  final key = progressPrefsKey(uid);
  Map<String, dynamic> store = {'version': 1, 'papers': <String, dynamic>{}};
  final raw = p.getString(key);
  if (raw != null && raw.isNotEmpty) {
    try {
      final decoded = jsonDecode(raw);
      if (decoded is Map && decoded['version'] == 1) {
        store = Map<String, dynamic>.from(decoded);
      }
    } catch (_) {
      // overwrite corrupt store
    }
  }
  final papers = Map<String, dynamic>.from(
    (store['papers'] is Map) ? store['papers'] as Map : <String, dynamic>{},
  );
  String text(Object? v) => (v is String) ? v.trim() : '';
  var changed = 0;
  for (final e in incoming.entries) {
    final cid = e.key.trim();
    if (cid.isEmpty) continue;
    final rowKey = progressCacheKey(cid);
    final mine = (papers[rowKey] is Map)
        ? Map<String, dynamic>.from(papers[rowKey] as Map)
        : <String, dynamic>{};
    final theirs = e.value;
    final next = Map<String, dynamic>.from(mine);
    final theirSpot = theirs.containsKey('sentence_index') &&
        theirs.containsKey('figure_index');
    if (theirSpot && text(theirs['at']).compareTo(text(mine['at'])) > 0) {
      for (final k in const [
        'sentence_index',
        'figure_index',
        'layout_mode',
        'section_label',
        'at',
      ]) {
        if (theirs.containsKey(k)) {
          next[k] = theirs[k];
        } else {
          next.remove(k);
        }
      }
    }
    final left = text(theirs['last_read_left_at']);
    if (left.compareTo(text(mine['last_read_left_at'])) > 0) {
      next['last_read_left_at'] = left;
    }
    if (jsonEncode(next) != jsonEncode(mine)) {
      papers[rowKey] = next;
      changed += 1;
    }
  }
  if (changed == 0) return 0;
  store['papers'] = papers;
  store['version'] = 1;
  await p.setString(key, jsonEncode(store));
  return changed;
}

/// design/411 — the newest spot another device of this account read, per paper.
///
/// Kept apart from this device's rows: an open validates its own row and refuses
/// a bad one, so a spot from elsewhere is only used when it is newer and fits.
String remoteSpotsPrefsKey(String? uid) =>
    'reading_spots_remote_v1:${(uid ?? '').trim().isEmpty ? '_' : uid!.trim()}';

typedef RemoteSpot = ({int si, int fi, String at});

Future<Map<String, Map<String, dynamic>>> _loadRemoteSpots(SharedPreferences p, String? uid) async {
  final raw = p.getString(remoteSpotsPrefsKey(uid));
  if (raw == null || raw.isEmpty) return {};
  try {
    final map = jsonDecode(raw);
    if (map is! Map) return {};
    return {
      for (final e in map.entries)
        if (e.value is Map) '${e.key}': Map<String, dynamic>.from(e.value as Map),
    };
  } catch (_) {
    return {};
  }
}

/// Store [spot] for [cacheId] when it is newer than the one held; returns whether it was.
Future<bool> saveRemoteSpot({
  required String? uid,
  required String cacheId,
  required RemoteSpot spot,
}) async {
  final cid = cacheId.trim();
  if (cid.isEmpty || spot.at.isEmpty) return false;
  final p = await SharedPreferences.getInstance();
  final all = await _loadRemoteSpots(p, uid);
  final held = '${all[cid]?['at'] ?? ''}';
  if (held.compareTo(spot.at) >= 0) return false;
  all[cid] = {'si': spot.si, 'fi': spot.fi, 'at': spot.at};
  if (all.length > 500) {
    final keys = all.keys.toList()
      ..sort((a, b) => '${all[a]!['at']}'.compareTo('${all[b]!['at']}'));
    for (final k in keys.take(all.length - 500)) {
      all.remove(k);
    }
  }
  await p.setString(remoteSpotsPrefsKey(uid), jsonEncode(all));
  return true;
}

Future<RemoteSpot?> loadRemoteSpot({required String? uid, required String cacheId}) async {
  final p = await SharedPreferences.getInstance();
  final row = (await _loadRemoteSpots(p, uid))[cacheId.trim()];
  if (row == null) return null;
  final si = row['si'];
  final fi = row['fi'];
  final at = '${row['at'] ?? ''}';
  if (si is! int || fi is! int || at.isEmpty) return null;
  return (si: si, fi: fi, at: at);
}

/// `at` of this device's own row for [cacheId] ('' when none).
Future<String> loadProgressAt({required String? uid, required String cacheId}) async {
  final rows = await loadProgressRows(uid: uid);
  return '${rows[cacheId.trim()]?['at'] ?? ''}';
}