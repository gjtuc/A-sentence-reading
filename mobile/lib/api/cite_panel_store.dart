/// Persist cite References panel opt-in (design/148).
library;

import 'package:shared_preferences/shared_preferences.dart';

import 'cite_panel_models.dart';

abstract class CitePanelStore {
  Future<String?> readRaw(String? uid);
  Future<void> writeRaw(String? uid, String raw);
}

class PrefsCitePanelStore implements CitePanelStore {
  PrefsCitePanelStore({SharedPreferences? prefs}) : _prefs = prefs;

  SharedPreferences? _prefs;

  Future<SharedPreferences> _ready() async {
    return _prefs ??= await SharedPreferences.getInstance();
  }

  @override
  Future<String?> readRaw(String? uid) async {
    final p = await _ready();
    return p.getString(citePanelPrefsKey(uid));
  }

  @override
  Future<void> writeRaw(String? uid, String raw) async {
    final p = await _ready();
    await p.setString(citePanelPrefsKey(uid), raw);
  }
}
