/// Cite References panel opt-in prefs (design/148).
///
/// WHY pure Dart: unit-test without SharedPreferences.
/// EDGE: missing/garbage → **true** (product default ON).
library;

const String kCitePanelPrefsKeyBase = 'asr.cite_panel.v1';

String citePanelPrefsKey(String? uid) {
  final u = (uid ?? '').trim();
  if (u.isEmpty) return kCitePanelPrefsKeyBase;
  return '$kCitePanelPrefsKeyBase.$u';
}

bool parseCitePanelEnabledPref(String? raw) {
  final s = (raw ?? '').trim();
  if (s.isEmpty) return true;
  final lower = s.toLowerCase();
  if (lower == '1' || lower == 'true' || lower == 'yes' || lower == 'on') {
    return true;
  }
  if (lower == '0' || lower == 'false' || lower == 'no' || lower == 'off') {
    return false;
  }
  if (s.startsWith('{')) {
    final on =
        RegExp(r'"enabled"\s*:\s*true', caseSensitive: false).hasMatch(s);
    final off =
        RegExp(r'"enabled"\s*:\s*false', caseSensitive: false).hasMatch(s);
    if (on) return true;
    if (off) return false;
  }
  // WHY fail-open: unknown blob must not hide panel by default.
  return true;
}

String serializeCitePanelEnabledPref(bool enabled) {
  return '{"enabled":${enabled ? 'true' : 'false'}}';
}
