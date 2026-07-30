/// Theme preference helpers (design/66).
///
/// WHY pure Dart: unit-test parse/serialize without SharedPreferences plugin.
library;

import 'package:flutter/material.dart';

/// Wire labels stored in prefs (stable ASCII).
const String kThemePrefSystem = 'system';
const String kThemePrefLight = 'light';
const String kThemePrefDark = 'dark';

const String kThemePrefsKey = 'asr.theme.v1';

/// Map a prefs string → [ThemeMode].
///
/// EDGE: null/empty/garbage/unknown → [ThemeMode.system].
ThemeMode parseThemeModePref(String? raw) {
  final s = (raw ?? '').trim().toLowerCase();
  if (s.isEmpty) return ThemeMode.system;
  switch (s) {
    case kThemePrefLight:
    case 'lite': // EDGE: common typo
      return ThemeMode.light;
    case kThemePrefDark:
    case 'night':
      return ThemeMode.dark;
    case kThemePrefSystem:
    case 'auto':
    case 'default':
      return ThemeMode.system;
    default:
      return ThemeMode.system;
  }
}

/// Stable prefs label for [mode].
String serializeThemeModePref(ThemeMode mode) {
  switch (mode) {
    case ThemeMode.light:
      return kThemePrefLight;
    case ThemeMode.dark:
      return kThemePrefDark;
    case ThemeMode.system:
      return kThemePrefSystem;
  }
}

/// Short Korean label for UI.
String themeModeLabelKo(ThemeMode mode) {
  switch (mode) {
    case ThemeMode.light:
      return '밝음';
    case ThemeMode.dark:
      return '어둠';
    case ThemeMode.system:
      return '시스템';
  }
}
