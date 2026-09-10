/// design/212 — growing chunk density without Gemini rebuild.
library;

/// Soft density relative to base Gemini/fallback plan. Positive = finer.
const int kChunkDensityMin = -2;
const int kChunkDensityMax = 2;

int clampChunkDensity(int d) {
  if (d < kChunkDensityMin) return kChunkDensityMin;
  if (d > kChunkDensityMax) return kChunkDensityMax;
  return d;
}

List<String> _words(String s) =>
    s.trim().split(RegExp(r'\s+')).where((w) => w.isNotEmpty).toList();

/// Insert mid prefixes (finer) or drop middle steps (coarser).
List<String> effectiveChunks(List<String> base, int density) {
  if (base.isEmpty) return const [];
  var cur = List<String>.from(base);
  final d = clampChunkDensity(density);
  if (d > 0) {
    for (var i = 0; i < d; i++) {
      final next = _finerOnce(cur);
      if (next == null) break;
      cur = next;
    }
  } else if (d < 0) {
    for (var i = 0; i < -d; i++) {
      final next = _coarserOnce(cur);
      if (next == null) break;
      cur = next;
    }
  }
  return cur;
}

bool canFiner(List<String> base, int density) {
  final cur = effectiveChunks(base, density);
  return _finerOnce(cur) != null;
}

bool canCoarser(List<String> base, int density) {
  final cur = effectiveChunks(base, density);
  return _coarserOnce(cur) != null;
}

List<String>? _finerOnce(List<String> chunks) {
  if (chunks.length < 2) {
    // Single full sentence: try half-prefix if long enough.
    final full = chunks.isEmpty ? '' : chunks.last;
    final w = _words(full);
    if (w.length < 4) return null;
    final mid = w.sublist(0, w.length ~/ 2).join(' ');
    if (mid.isEmpty || mid == full) return null;
    return [mid, full];
  }
  for (var i = 0; i < chunks.length - 1; i++) {
    final a = chunks[i];
    final b = chunks[i + 1];
    if (!b.startsWith(a) && !b.toLowerCase().startsWith(a.toLowerCase())) {
      continue;
    }
    final aw = _words(a);
    final bw = _words(b);
    if (bw.length - aw.length < 4) continue; // soft: need room to split
    final midN = aw.length + ((bw.length - aw.length) ~/ 2);
    if (midN <= aw.length || midN >= bw.length) continue;
    final mid = bw.sublist(0, midN).join(' ');
    if (mid == a || mid == b) continue;
    return [...chunks.sublist(0, i + 1), mid, ...chunks.sublist(i + 1)];
  }
  return null;
}

List<String>? _coarserOnce(List<String> chunks) {
  if (chunks.length <= 2) return null; // soft min: keep at least 2 when possible
  if (chunks.length == 1) return null;
  // Drop a middle step (not first, not last).
  final drop = chunks.length ~/ 2;
  if (drop <= 0 || drop >= chunks.length - 1) return null;
  return [...chunks.sublist(0, drop), ...chunks.sublist(drop + 1)];
}

/// Rematch index after density change by longest prefix match of previous text.
int rematchChunkIndex(List<String> newChunks, String previousText, int fallback) {
  if (newChunks.isEmpty) return 0;
  final prev = previousText.trim();
  if (prev.isEmpty) {
    return fallback.clamp(0, newChunks.length - 1);
  }
  var best = 0;
  var bestLen = -1;
  for (var i = 0; i < newChunks.length; i++) {
    final c = newChunks[i].trim();
    if (c == prev) return i;
    if (prev.startsWith(c) && c.length > bestLen) {
      best = i;
      bestLen = c.length;
    }
    if (c.startsWith(prev) && prev.length > bestLen) {
      best = i;
      bestLen = prev.length;
    }
  }
  if (bestLen >= 0) return best;
  return fallback.clamp(0, newChunks.length - 1);
}
