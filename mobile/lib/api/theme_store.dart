/// Persist theme preference (design/66).
library;

import 'package:shared_preferences/shared_preferences.dart';

import 'theme_models.dart';

abstract class ThemeStore {
  Future<String?> readRaw();

  Future<void> writeRaw(String value);
}

class PrefsThemeStore implements ThemeStore {
  PrefsThemeStore({SharedPreferences? prefs}) : _prefs = prefs;

  SharedPreferences? _prefs;

  Future<SharedPreferences> _ready() async {
    return _prefs ??= await SharedPreferences.getInstance();
  }

  @override
  Future<String?> readRaw() async {
    final p = await _ready();
    return p.getString(kThemePrefsKey);
  }

  @override
  Future<void> writeRaw(String value) async {
    final p = await _ready();
    final v = value.trim();
    // EDGE: blank → remove key so next load uses system default
    if (v.isEmpty) {
      await p.remove(kThemePrefsKey);
      return;
    }
    await p.setString(kThemePrefsKey, v);
  }
}

/// In-memory store for unit/widget tests.
class MemoryThemeStore implements ThemeStore {
  String? _raw;

  @override
  Future<String?> readRaw() async => _raw;

  @override
  Future<void> writeRaw(String value) async {
    final v = value.trim();
    _raw = v.isEmpty ? null : v;
  }
}
