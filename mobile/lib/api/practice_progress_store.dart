/// design/246 — per-paper practice sentence cursor (orthogonal to reading progress).
library;

import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

const String kPracticeProgressPrefsKeyBase = 'asr.practice_progress.v1';

String practiceProgressPrefsKey(String? uid) {
  final u = (uid ?? '').trim();
  if (u.isEmpty) return kPracticeProgressPrefsKeyBase;
  final safe = u.length > 128 ? u.substring(0, 128) : u;
  return '$kPracticeProgressPrefsKeyBase.u.$safe';
}

String practiceProgressCacheKey(String cacheId) => 'cache:${cacheId.trim()}';

class PracticeProgressRow {
  const PracticeProgressRow({
    required this.sentenceIndex,
    this.chunkIndex = 0,
    this.sectionLabel = '',
  });

  final int sentenceIndex;
  final int chunkIndex;
  final String sectionLabel;
}

Future<PracticeProgressRow?> loadPracticeProgress({
  required String? uid,
  required String cacheId,
}) async {
  final cid = cacheId.trim();
  if (cid.isEmpty) return null;
  final p = await SharedPreferences.getInstance();
  final raw = p.getString(practiceProgressPrefsKey(uid));
  if (raw == null || raw.isEmpty) return null;
  try {
    final map = jsonDecode(raw);
    if (map is! Map) return null;
    final papers = map['papers'];
    if (papers is! Map) return null;
    final row = papers[practiceProgressCacheKey(cid)];
    if (row is! Map) return null;
    final si = row['sentence_index'];
    if (si is! num) return null;
    final ci = row['chunk_index'];
    final chunk = ci is num ? ci.toInt() : 0;
    return PracticeProgressRow(
      sentenceIndex: si.toInt(),
      chunkIndex: chunk < 0 ? 0 : chunk,
      sectionLabel: '${row['section_label'] ?? ''}'.trim(),
    );
  } catch (_) {
    return null;
  }
}

Future<void> savePracticeProgress({
  required String? uid,
  required String cacheId,
  required int sentenceIndex,
  int chunkIndex = 0,
  String sectionLabel = '',
}) async {
  final cid = cacheId.trim();
  if (cid.isEmpty) return;
  if (sentenceIndex < 0) return;
  final p = await SharedPreferences.getInstance();
  final key = practiceProgressPrefsKey(uid);
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
    } catch (_) {}
  }
  final papers = Map<String, dynamic>.from(
    (store['papers'] as Map?) ?? <String, dynamic>{},
  );
  papers[practiceProgressCacheKey(cid)] = {
    'sentence_index': sentenceIndex,
    'chunk_index': chunkIndex < 0 ? 0 : chunkIndex,
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

/// Clamp stored practice cursor against paper size (soft — unlike reading fail-closed).
PracticeProgressRow? clampPracticeProgress({
  required PracticeProgressRow? raw,
  required int sentenceCount,
  int chunkCount = 1,
}) {
  if (raw == null || sentenceCount < 1) return null;
  final si = raw.sentenceIndex;
  if (si < 0 || si >= sentenceCount) return null;
  final maxChunk = chunkCount < 1 ? 0 : chunkCount - 1;
  final ci = raw.chunkIndex.clamp(0, maxChunk);
  return PracticeProgressRow(
    sentenceIndex: si,
    chunkIndex: ci,
    sectionLabel: raw.sectionLabel,
  );
}

/// Batch load practice resume labels for library rows (section only).
Future<Map<String, String>> loadPracticeResumeLabels({
  required String? uid,
  required Iterable<String> cacheIds,
}) async {
  final out = <String, String>{};
  final want = {for (final id in cacheIds) id.trim()}.difference({''});
  if (want.isEmpty) return out;
  final p = await SharedPreferences.getInstance();
  final raw = p.getString(practiceProgressPrefsKey(uid));
  if (raw == null || raw.isEmpty) return out;
  try {
    final map = jsonDecode(raw);
    if (map is! Map) return out;
    final papers = map['papers'];
    if (papers is! Map) return out;
    for (final cid in want) {
      final row = papers[practiceProgressCacheKey(cid)];
      if (row is! Map) continue;
      final si = row['sentence_index'];
      if (si is! num) continue;
      final section = (row['section_label']?.toString() ?? '').trim();
      if (section.isNotEmpty) {
        out[cid] = section;
      }
    }
  } catch (_) {}
  return out;
}
