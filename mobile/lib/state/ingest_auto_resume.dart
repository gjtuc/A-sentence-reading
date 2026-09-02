/// design/158+ — stage-scoped auto 「이어서 분석하기」 after poll/HTTP timeout.
///
/// Same normalized stage → consecutive timeout count; max [kIngestAutoResumeMax]
/// auto resumes, then user must tap. New stage key resets the counter.
library;

/// Max automatic resumeAnalysis calls per consecutive same-stage timeout streak.
const int kIngestAutoResumeMax = 3;

/// Coarse stage key from upload progress message (digits/fractions stripped).
String normalizeIngestStageKey(String stage, {int? percent}) {
  var s = stage.trim().toLowerCase();
  if (s.isEmpty) {
    if (percent == null) return 'unknown';
    final band = (percent.clamp(0, 100) ~/ 10) * 10;
    return 'pct_$band';
  }
  final rawParts = s.split('·');
  final parts = <String>[];
  for (final raw in rawParts) {
    var t = raw.trim();
    t = t.replaceAll(RegExp(r'\d+\s*/\s*\d+'), ' ');
    t = t.replaceAll(RegExp(r'\d+%?'), ' ');
    t = t.replaceAll('%', ' ');
    t = t.replaceAll(RegExp(r'\s+'), ' ').trim();
    if (t.isNotEmpty) parts.add(t);
  }
  bool skipGeneric(String p) {
    if (p == '처리 중' || p == '처리중' || p == '처리') return true;
    if (p.startsWith('클라우드')) return true;
    return false;
  }
  // Prefer action segment (middle): 「조각 올리는 중」「페이지 이미지 읽는 중」.
  for (final p in parts) {
    if (skipGeneric(p)) continue;
    return p.length > 48 ? p.substring(0, 48) : p;
  }
  if (parts.isNotEmpty) {
    final p = parts.first;
    return p.length > 48 ? p.substring(0, 48) : p;
  }
  if (percent == null) return 'unknown';
  final band = (percent.clamp(0, 100) ~/ 10) * 10;
  return 'pct_$band';
}

/// Mutable gate: call [noteTimeout] on each timeout; [true] → auto-resume.
class IngestAutoResumeGate {
  String? stageKey;
  int consecutiveTimeouts = 0;

  void reset() {
    stageKey = null;
    consecutiveTimeouts = 0;
  }

  /// Progress reached a different stage → clear streak.
  void noteProgress(String key) {
    final k = key.trim();
    if (k.isEmpty) return;
    if (stageKey != null && k != stageKey) {
      reset();
    }
  }

  /// Record a timeout for [key]. Returns whether to auto-call resumeAnalysis.
  bool noteTimeout(String key) {
    final k = key.trim().isEmpty ? 'unknown' : key.trim();
    if (stageKey == k) {
      consecutiveTimeouts += 1;
    } else {
      stageKey = k;
      consecutiveTimeouts = 1;
    }
    return consecutiveTimeouts <= kIngestAutoResumeMax;
  }
}
