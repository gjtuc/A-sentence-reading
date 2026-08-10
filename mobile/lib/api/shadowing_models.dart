/// Shadowing practice opt-in prefs (design/79).
///
/// WHY pure Dart: unit-test without SharedPreferences.
/// EDGE: missing/garbage → **false** (product default OFF).
library;

/// Base key; append `.{uid}` when logged in so accounts on one device do not share.
const String kShadowingPrefsKeyBase = 'asr.shadowing.v1';

String shadowingPrefsKey(String? uid) {
  final u = (uid ?? '').trim();
  if (u.isEmpty) return kShadowingPrefsKeyBase;
  return '$kShadowingPrefsKeyBase.$u';
}

/// Parse stored JSON or legacy plain bool/string → enabled flag.
bool parseShadowingEnabledPref(String? raw) {
  final s = (raw ?? '').trim();
  if (s.isEmpty) return false;
  final lower = s.toLowerCase();
  if (lower == '1' || lower == 'true' || lower == 'yes' || lower == 'on') {
    return true;
  }
  if (lower == '0' || lower == 'false' || lower == 'no' || lower == 'off') {
    return false;
  }
  // JSON {"enabled": true}
  if (s.startsWith('{')) {
    final on = RegExp(r'"enabled"\s*:\s*true', caseSensitive: false).hasMatch(s);
    final off = RegExp(r'"enabled"\s*:\s*false', caseSensitive: false).hasMatch(s);
    if (on) return true;
    if (off) return false;
  }
  // WHY fail-closed: unknown blob must not turn practice on.
  return false;
}

String serializeShadowingEnabledPref(bool enabled) {
  return '{"enabled":${enabled ? 'true' : 'false'}}';
}
