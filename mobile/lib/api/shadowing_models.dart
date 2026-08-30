/// Shadowing practice opt-in prefs (design/79 · design/160 auto-off).
///
/// WHY pure Dart: unit-test without SharedPreferences.
/// EDGE: missing/garbage → **false** (product default OFF).
library;

import 'dart:convert';

/// Base key; append `.{uid}` when logged in so accounts on one device do not share.
const String kShadowingPrefsKeyBase = 'asr.shadowing.v1';

/// Auto-off when practice unused for this long (design/160).
const Duration kShadowingAutoOffAfter = Duration(days: 90);

String shadowingPrefsKey(String? uid) {
  final u = (uid ?? '').trim();
  if (u.isEmpty) return kShadowingPrefsKeyBase;
  return '$kShadowingPrefsKeyBase.$u';
}

class ShadowingPrefs {
  const ShadowingPrefs({
    this.enabled = false,
    this.enabledSince = '',
    this.lastPracticePressedAt = '',
  });

  final bool enabled;
  final String enabledSince;
  final String lastPracticePressedAt;

  ShadowingPrefs copyWith({
    bool? enabled,
    String? enabledSince,
    String? lastPracticePressedAt,
  }) {
    return ShadowingPrefs(
      enabled: enabled ?? this.enabled,
      enabledSince: enabledSince ?? this.enabledSince,
      lastPracticePressedAt:
          lastPracticePressedAt ?? this.lastPracticePressedAt,
    );
  }
}

/// Parse stored JSON or legacy plain bool/string → prefs.
ShadowingPrefs parseShadowingPrefs(String? raw) {
  final s = (raw ?? '').trim();
  if (s.isEmpty) return const ShadowingPrefs();
  final lower = s.toLowerCase();
  if (lower == '1' || lower == 'true' || lower == 'yes' || lower == 'on') {
    return const ShadowingPrefs(enabled: true);
  }
  if (lower == '0' || lower == 'false' || lower == 'no' || lower == 'off') {
    return const ShadowingPrefs();
  }
  if (s.startsWith('{')) {
    try {
      final decoded = jsonDecode(s);
      if (decoded is Map) {
        final enabled = decoded['enabled'] == true;
        return ShadowingPrefs(
          enabled: enabled,
          enabledSince: '${decoded['enabled_since'] ?? ''}'.trim(),
          lastPracticePressedAt:
              '${decoded['last_practice_pressed_at'] ?? ''}'.trim(),
        );
      }
    } catch (_) {
      // fall through
    }
  }
  return const ShadowingPrefs();
}

/// Legacy helper — enabled bit only.
bool parseShadowingEnabledPref(String? raw) =>
    parseShadowingPrefs(raw).enabled;

String serializeShadowingPrefs(ShadowingPrefs prefs) {
  return jsonEncode({
    'enabled': prefs.enabled,
    if (prefs.enabledSince.isNotEmpty) 'enabled_since': prefs.enabledSince,
    if (prefs.lastPracticePressedAt.isNotEmpty)
      'last_practice_pressed_at': prefs.lastPracticePressedAt,
  });
}

String serializeShadowingEnabledPref(bool enabled) =>
    serializeShadowingPrefs(ShadowingPrefs(enabled: enabled));

/// design/160 — OFF when enabled but no practice press within 90d.
bool shouldAutoOffShadowing(ShadowingPrefs prefs) {
  if (!prefs.enabled) return false;
  final now = DateTime.now().toUtc();
  final anchor = prefs.lastPracticePressedAt.isNotEmpty
      ? DateTime.tryParse(prefs.lastPracticePressedAt)
      : (prefs.enabledSince.isNotEmpty
          ? DateTime.tryParse(prefs.enabledSince)
          : null);
  if (anchor == null) return false;
  return now.difference(anchor.toUtc()) > kShadowingAutoOffAfter;
}
