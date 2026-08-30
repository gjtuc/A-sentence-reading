/// App semver compare for settings update row (design/161).
library;

/// Parse `0.3.94` style labels into non-negative int segments.
List<int> parseAppVersionSegments(String raw) {
  final s = raw.trim();
  if (s.isEmpty) return const [];
  final parts = s.split('.');
  final out = <int>[];
  for (final part in parts) {
    final t = part.trim();
    if (t.isEmpty || !RegExp(r'^\d+$').hasMatch(t)) return const [];
    out.add(int.parse(t));
  }
  return out;
}

/// -1 local older · 0 equal · +1 local newer · null if either unparsable.
int? compareAppVersions(String local, String remote) {
  final a = parseAppVersionSegments(local);
  final b = parseAppVersionSegments(remote);
  if (a.isEmpty || b.isEmpty) return null;
  final n = a.length > b.length ? a.length : b.length;
  for (var i = 0; i < n; i++) {
    final av = i < a.length ? a[i] : 0;
    final bv = i < b.length ? b[i] : 0;
    if (av < bv) return -1;
    if (av > bv) return 1;
  }
  return 0;
}

bool isUpdateAvailable(String local, String remote) =>
    compareAppVersions(local, remote) == -1;
