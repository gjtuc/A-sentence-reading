/// Shadowing chunk plan helpers (practice boot / skip-empty).
///
/// Plan shape: `{ status, sentences: { sid: { chunks: [..] } } }`.
/// design/266 — playable = plan-row chunks only (no EN plain fallback).
library;

/// Chunks from plan row only (empty if missing / empty list).
List<String> shadowingPlanChunksForSentence(
  Map<String, dynamic>? plan,
  String sentenceId,
) {
  final sid = sentenceId.trim();
  final sentences = plan?['sentences'];
  if (sid.isEmpty || sentences is! Map) return const [];
  final row = sentences[sid];
  if (row is! Map) return const [];
  final ch = row['chunks'];
  if (ch is! List || ch.isEmpty) return const [];
  return ch.map((e) => e.toString()).where((e) => e.trim().isNotEmpty).toList();
}

/// Count sids with non-empty plan chunks.
int countShadowingReadySentences(Map<String, dynamic>? plan) {
  final sentences = plan?['sentences'];
  if (sentences is! Map) return 0;
  var n = 0;
  for (final v in sentences.values) {
    if (v is! Map) continue;
    final ch = v['chunks'];
    if (ch is List && ch.any((e) => e.toString().trim().isNotEmpty)) {
      n += 1;
    }
  }
  return n;
}

bool shadowingPlanStatusIsOk(Map<String, dynamic>? plan) =>
    plan?['status']?.toString() == 'ok';

bool shadowingPlanStatusIsPending(Map<String, dynamic>? plan) =>
    plan?['status']?.toString() == 'pending';

/// Practice bind/skip: plan chunks. Optional plain fallback for legacy callers only.
List<String> shadowingChunksForSentence(
  Map<String, dynamic>? plan,
  String sentenceId,
  String plain, {
  bool allowPlainFallback = false,
}) {
  final planned = shadowingPlanChunksForSentence(plan, sentenceId);
  if (planned.isNotEmpty) return planned;
  if (!allowPlainFallback) return const [];
  final t = plain.trim();
  return t.isEmpty ? <String>[] : <String>[t];
}

/// Steps to advance from [fromIndex] to the next playable sentence.
///
/// Returns `0` if [fromIndex] already has plan chunks, a positive delta to skip
/// empty rows, or `-1` if nothing playable remains (including [fromIndex]).
int shadowingSkipEmptyDelta({
  required Map<String, dynamic>? plan,
  required List<({String id, String text})> sentences,
  required int fromIndex,
}) {
  if (sentences.isEmpty) return -1;
  if (fromIndex < 0 || fromIndex >= sentences.length) return -1;
  for (var i = fromIndex; i < sentences.length; i++) {
    final s = sentences[i];
    final sid = s.id.trim().isNotEmpty ? s.id : '$i';
    final chunks = shadowingPlanChunksForSentence(plan, sid);
    if (chunks.isNotEmpty) {
      return i - fromIndex;
    }
  }
  return -1;
}

/// Sentences already planned, for the next build request. Null if none.
Map<String, dynamic>? shadowingPriorSentences(Map<String, dynamic>? plan) {
  final sentences = plan?['sentences'];
  if (sentences is! Map) return null;
  final out = <String, dynamic>{};
  for (final entry in sentences.entries) {
    final sid = '${entry.key}';
    final chunks = shadowingPlanChunksForSentence(plan, sid);
    if (chunks.isEmpty) continue;
    final row = entry.value;
    final text = row is Map ? '${row['text'] ?? ''}'.trim() : '';
    if (text.isEmpty) continue;
    out[sid] = {'text': text, 'chunks': chunks};
  }
  return out.isEmpty ? null : out;
}

/// True when every non-empty [expected] sentence is present with the same chunks.
bool shadowingPlanRetainsSentences(
  Map<String, dynamic>? saved,
  Map<String, dynamic>? expected,
) {
  final sentences = expected?['sentences'];
  if (sentences is! Map) return true;
  for (final entry in sentences.entries) {
    final chunks = shadowingPlanChunksForSentence(expected, '${entry.key}');
    if (chunks.isEmpty) continue;
    final got = shadowingPlanChunksForSentence(saved, '${entry.key}');
    if (got.length != chunks.length) return false;
    for (var i = 0; i < chunks.length; i++) {
      if (got[i] != chunks[i]) return false;
    }
  }
  return true;
}
Map<String, dynamic> mergeShadowingPlans(
  Map<String, dynamic>? base,
  Map<String, dynamic> incoming,
) {
  final out = Map<String, dynamic>.from(base ?? const {});
  out['status'] = incoming['status'] ?? out['status'];
  if (incoming['progress'] != null) out['progress'] = incoming['progress'];
  final baseSent = out['sentences'];
  final inSent = incoming['sentences'];
  final merged = <String, dynamic>{};
  if (baseSent is Map) {
    for (final e in baseSent.entries) {
      merged['${e.key}'] = e.value is Map
          ? Map<String, dynamic>.from(e.value as Map)
          : e.value;
    }
  }
  if (inSent is Map) {
    for (final e in inSent.entries) {
      merged['${e.key}'] = e.value is Map
          ? Map<String, dynamic>.from(e.value as Map)
          : e.value;
    }
  }
  out['sentences'] = merged;
  return out;
}
