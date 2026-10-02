/// design/385 — build reference sounds from the sentence about to be read.
library;

/// Where to start walking. Practice wins when it is a real index: that is
/// the sentence the speaker will say, not the last reader page.
int soundWarmStart({
  required int readerIndex,
  int? practiceIndex,
  required int sentenceN,
}) {
  final practice = practiceIndex;
  if (practice != null && practice >= 0 && practice < sentenceN) {
    return practice;
  }
  if (readerIndex >= 0 && readerIndex < sentenceN) return readerIndex;
  return 0;
}

/// Rotate [texts] so index [from] is first, then wrap. Blanks are dropped
/// after the rotate so the cursor still points at the printed sentence.
List<String> soundWarmTexts(List<String> texts, {int from = 0}) {
  if (texts.isEmpty) return const [];
  final n = texts.length;
  var start = from;
  if (start < 0 || start >= n) start = 0;
  final out = <String>[];
  for (var i = 0; i < n; i++) {
    final one = texts[(start + i) % n].trim();
    if (one.isNotEmpty) out.add(one);
  }
  return out;
}
