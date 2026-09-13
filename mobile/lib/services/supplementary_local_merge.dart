/// design/263 — pure helpers for device-local SI merge (refs + figure ids).
library;

import '../api/cite_refs.dart';
import 'figure_disk_cache.dart';

/// Server parity: main.references or si.references (prefer main when both set).
List<dynamic> orMergeReferences(Object? mainRefs, Object? siRefs) {
  if (mainRefs is List && mainRefs.isNotEmpty) return List<dynamic>.from(mainRefs);
  if (siRefs is List && siRefs.isNotEmpty) return List<dynamic>.from(siRefs);
  return const [];
}

String rewriteSiFigureId(String rawId, {required int fallbackIndex}) {
  var fid = rawId.trim();
  if (fid.isEmpty) fid = 'si-fig-$fallbackIndex';
  if (!fid.startsWith('si-')) fid = 'si-$fid';
  return fid;
}

String figureFileRelForId(String figureId) {
  final safe = figureCacheSafeToken(figureId, maxLen: 64);
  if (safe.isEmpty) return '';
  return 'figures/$safe.png';
}

bool sentenceMatchesBibliography(String sentenceText, List<CiteRefEntry> refs) {
  final plain = stripTags(sentenceText).replaceAll(RegExp(r'\s+'), ' ').trim().toLowerCase();
  if (plain.length < 40 || refs.isEmpty) return false;
  for (final e in refs) {
    final ref =
        stripTags(e.text).replaceAll(RegExp(r'\s+'), ' ').trim().toLowerCase();
    if (ref.length < 12) continue;
    if (plain.contains(ref) || ref.contains(plain)) return true;
    final n = plain.length < ref.length ? plain.length : ref.length;
    final take = n > 80 ? 80 : n;
    if (take >= 40 && plain.substring(0, take) == ref.substring(0, take)) {
      return true;
    }
  }
  return false;
}

List<Map<String, dynamic>> filterSiSentencesAgainstRefs(
  List<Map<String, dynamic>> siSentences,
  List<CiteRefEntry> refs,
) {
  if (refs.isEmpty) return siSentences;
  return [
    for (final s in siSentences)
      if (!sentenceMatchesBibliography('${s['text'] ?? ''}', refs)) s,
  ];
}

Map<String, dynamic> rewriteSiFigureMeta(
  Map<String, dynamic> raw, {
  required int fallbackIndex,
}) {
  final m = Map<String, dynamic>.from(raw);
  final oldId = '${m['id'] ?? ''}'.trim();
  final newId = rewriteSiFigureId(oldId, fallbackIndex: fallbackIndex);
  m['id'] = newId;
  m['file'] = figureFileRelForId(newId);
  m['image_src'] = '';
  m['_prior_figure_id'] = oldId;
  return m;
}
