/// Persist translate opt-in (design/99).
library;

import 'package:shared_preferences/shared_preferences.dart';

import 'translate_models.dart';

abstract class TranslateStore {
  Future<String?> readRaw(String? uid);
  Future<void> writeRaw(String? uid, String raw);
}

class PrefsTranslateStore implements TranslateStore {
  PrefsTranslateStore({SharedPreferences? prefs}) : _prefs = prefs;

  SharedPreferences? _prefs;

  Future<SharedPreferences> _ready() async {
    return _prefs ??= await SharedPreferences.getInstance();
  }

  @override
  Future<String?> readRaw(String? uid) async {
    final p = await _ready();
    return p.getString(translatePrefsKey(uid));
  }

  @override
  Future<void> writeRaw(String? uid, String raw) async {
    final p = await _ready();
    await p.setString(translatePrefsKey(uid), raw);
  }
}
