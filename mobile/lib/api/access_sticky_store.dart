/// Per-uid last-known access unlock (design/172).
///
/// WHY: under Cloud Run load, /api/access/status can time out; sticky keeps
/// previously Allowed users in the main shell instead of 「승인 대기」.
library;

import 'package:shared_preferences/shared_preferences.dart';

const String _prefsPrefix = 'asr.access.sticky_allowed.v1.';

String _keyForUid(String uid) => '$_prefsPrefix${uid.trim()}';

/// Abstract store so unit tests can inject memory without Flutter plugins.
abstract class AccessStickyStore {
  Future<bool?> readAllowed(String uid);

  Future<void> writeAllowed(String uid, bool allowed);

  Future<void> clear(String uid);
}

class PrefsAccessStickyStore implements AccessStickyStore {
  PrefsAccessStickyStore({SharedPreferences? prefs}) : _prefs = prefs;

  SharedPreferences? _prefs;

  Future<SharedPreferences> _ready() async {
    return _prefs ??= await SharedPreferences.getInstance();
  }

  @override
  Future<bool?> readAllowed(String uid) async {
    final id = uid.trim();
    if (id.isEmpty) return null;
    final p = await _ready();
    if (!p.containsKey(_keyForUid(id))) return null;
    return p.getBool(_keyForUid(id));
  }

  @override
  Future<void> writeAllowed(String uid, bool allowed) async {
    final id = uid.trim();
    if (id.isEmpty) return;
    final p = await _ready();
    await p.setBool(_keyForUid(id), allowed);
  }

  @override
  Future<void> clear(String uid) async {
    final id = uid.trim();
    if (id.isEmpty) return;
    final p = await _ready();
    await p.remove(_keyForUid(id));
  }
}
