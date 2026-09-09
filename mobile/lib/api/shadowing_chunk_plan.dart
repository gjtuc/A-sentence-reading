/// Shadowing chunk plan helpers (practice boot / skip-empty).
///
/// Plan shape: `{ status, sentences: { sid: { chunks: [..] } } }`.
library;

List<String> shadowingChunksForSentence(
  Map<String, dynamic>? plan,
  String sentenceId,
  String plain,
) {
  final sid = sentenceId.trim();
  final sentences = plan?['sentences'];
  if (sid.isNotEmpty && sentences is Map && sentences[sid] is Map) {
    final row = sentences[sid] as Map;
    final ch = row['chunks'];
    if (ch is List && ch.isNotEmpty) {
      return ch.map((e) => e.toString()).toList();
    }
  }
  final t = plain.trim();
  return t.isEmpty ? <String>[] : <String>[t];
}

/// Steps to advance from [fromIndex] to the next playable sentence.
///
/// Returns `0` if [fromIndex] already has chunks, a positive delta to skip
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
    final chunks = shadowingChunksForSentence(plan, sid, s.text);
    if (chunks.isNotEmpty) {
      return i - fromIndex;
    }
  }
  return -1;
}
