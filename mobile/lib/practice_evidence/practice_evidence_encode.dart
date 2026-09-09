/// design/209 — encode practice cycle fields to evidence-safe details.
library;

/// Mirror of EvidenceBus / server `_safe_details` value rules.
Map<String, Object?> safePracticeDetails(Map<String, Object?> raw) {
  final out = <String, Object?>{};
  for (final e in raw.entries) {
    final key = e.key.trim();
    if (key.isEmpty || !RegExp(r'^[a-z][a-z0-9_]{0,39}$').hasMatch(key)) {
      continue;
    }
    final v = e.value;
    if (v is bool) {
      out[key] = v;
    } else if (v is int) {
      out[key] = v.clamp(-1000000000, 1000000000);
    } else if (v is double) {
      if (v.isNaN || v.isInfinite) continue;
      final clamped = v.clamp(-1e12, 1e12);
      out[key] = double.parse(clamped.toStringAsFixed(3));
    } else if (v is String) {
      final s = v.trim();
      if (s.isNotEmpty && RegExp(r'^[a-z][a-z0-9_]{0,63}$').hasMatch(s)) {
        out[key] = s;
      }
    }
  }
  return out;
}

String snakeToken(String raw, {String fallback = 'x'}) {
  final t = raw
      .trim()
      .toLowerCase()
      .replaceAll(RegExp(r'[^a-z0-9]+'), '_')
      .replaceAll(RegExp(r'_+'), '_')
      .replaceAll(RegExp(r'^_|_$'), '');
  if (t.isEmpty) return fallback;
  final s = t.startsWith(RegExp(r'[a-z]')) ? t : 'x$t';
  return s.length > 64 ? s.substring(0, 64) : s;
}

int voiceHash(String voice) {
  final s = voice.trim();
  if (s.isEmpty) return 0;
  var h = 0;
  for (final c in s.codeUnits) {
    h = (h * 31 + c) & 0x7fffffff;
  }
  return h == 0 ? 1 : h;
}

/// Build ingest envelope (not yet posted).
Map<String, dynamic> buildPracticeCycleEvent({
  required Map<String, Object?> details,
  required String cacheId,
  required String appVersion,
  required String traceId,
  required String sessionId,
  String code = 'ok',
  bool ok = true,
}) {
  return <String, dynamic>{
    'kind': 'practice_cycle_wide',
    'source': 'mobile',
    'severity': 'boundary',
    'trace_id': traceId,
    'session_id': sessionId,
    'app_version': appVersion,
    if (cacheId.isNotEmpty) 'cache_id': cacheId,
    'ok': ok,
    'code': snakeToken(code, fallback: 'ok'),
    'details': safePracticeDetails(details),
  };
}
