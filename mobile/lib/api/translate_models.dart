/// Translate opt-in prefs (design/99).
///
/// WHY pure Dart: unit-test without SharedPreferences.
/// EDGE: missing/garbage → **false** (product default OFF).
library;

/// Base key; append `.{uid}` when logged in so accounts on one device do not share.
const String kTranslatePrefsKeyBase = 'asr.translate.v1';

String translatePrefsKey(String? uid) {
  final u = (uid ?? '').trim();
  if (u.isEmpty) return kTranslatePrefsKeyBase;
  return '$kTranslatePrefsKeyBase.$u';
}

/// Parse stored JSON or legacy plain bool/string → enabled flag.
bool parseTranslateEnabledPref(String? raw) {
  final s = (raw ?? '').trim();
  if (s.isEmpty) return false;
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
  // WHY fail-closed: unknown blob must not turn translate on.
  return false;
}

String serializeTranslateEnabledPref(bool enabled) {
  return '{"enabled":${enabled ? 'true' : 'false'}}';
}
