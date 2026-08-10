/// Persist shadowing opt-in (design/79).
library;

import 'package:shared_preferences/shared_preferences.dart';

import 'shadowing_models.dart';

abstract class ShadowingStore {
  Future<String?> readRaw(String? uid);
  Future<void> writeRaw(String? uid, String raw);
}

class PrefsShadowingStore implements ShadowingStore {
  PrefsShadowingStore({SharedPreferences? prefs}) : _prefs = prefs;

  SharedPreferences? _prefs;

  Future<SharedPreferences> _ready() async {
    return _prefs ??= await SharedPreferences.getInstance();
  }

  @override
  Future<String?> readRaw(String? uid) async {
    final p = await _ready();
    return p.getString(shadowingPrefsKey(uid));
  }

  @override
  Future<void> writeRaw(String? uid, String raw) async {
    final p = await _ready();
    await p.setString(shadowingPrefsKey(uid), raw);
  }
}
