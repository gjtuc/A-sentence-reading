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
Future<void> saveProgressRow({
  required String? uid,
  required String cacheId,
  required int sentenceIndex,
  required int figureIndex,
  String layoutMode = '',
  String sectionLabel = '',
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
  papers[progressCacheKey(cid)] = {
    'sentence_index': sentenceIndex,
    'figure_index': figureIndex,
    if (layoutMode.trim().isNotEmpty) 'layout_mode': layoutMode.trim(),
    if (sectionLabel.trim().isNotEmpty) 'section_label': sectionLabel.trim(),
    'at': DateTime.now().toUtc().toIso8601String(),
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
      final section = '${row['section_label'] ?? ''}'.trim();
      final label =
          '문장 ${si.toInt() + 1} · 그림 ${fi.toInt() + 1}'
          '${section.isNotEmpty ? ' · $section' : ''}'
          ' 읽는 중';
      out[cid] = label;
    }
  } catch (_) {
    return out;
  }
  return out;
}
