/// App theme mode controller (design/66).
///
/// Live Enable / IPS stay out of ASR (Trading Gate).
library;

import 'package:flutter/material.dart';

import '../api/theme_models.dart';
import '../api/theme_store.dart';

class ThemeController extends ChangeNotifier {
  ThemeController({ThemeStore? store}) : _store = store ?? PrefsThemeStore();

  final ThemeStore _store;

  ThemeMode mode = ThemeMode.system;
  bool ready = false;
  String? error;

  /// Load prefs once at cold start.
  Future<void> bootstrap() async {
    try {
      final raw = await _store.readRaw();
      mode = parseThemeModePref(raw);
      error = null;
    } catch (e) {
      // EDGE: plugin failure → system theme, keep app usable
      mode = ThemeMode.system;
      error = e.toString();
    } finally {
      ready = true;
      notifyListeners();
    }
  }

  Future<void> setMode(ThemeMode next) async {
    mode = next;
    notifyListeners();
    try {
      await _store.writeRaw(serializeThemeModePref(next));
      error = null;
    } catch (e) {
      // EDGE: persist fail — UI already updated; surface message
      error = e.toString();
      notifyListeners();
    }
  }
}
