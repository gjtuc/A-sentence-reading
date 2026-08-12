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
  });

  final Object? sentenceIndex;
  final Object? figureIndex;
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
