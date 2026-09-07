/// design/176 — local store for focus practice daily state.
library;

import 'package:shared_preferences/shared_preferences.dart';

import 'focus_practice_models.dart';

abstract class FocusPracticeStore {
  Future<String?> readRaw(String? uid);
  Future<void> writeRaw(String? uid, String raw);
}

class PrefsFocusPracticeStore implements FocusPracticeStore {
  @override
  Future<String?> readRaw(String? uid) async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(focusPracticePrefsKey(uid));
  }

  @override
  Future<void> writeRaw(String? uid, String raw) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(focusPracticePrefsKey(uid), raw);
  }
}
