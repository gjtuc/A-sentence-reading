/// Persist soft-hidden papers until wall-clock purge (design/224).
library;

import 'package:shared_preferences/shared_preferences.dart';

import 'library_soft_delete_models.dart';

abstract class LibrarySoftDeleteStore {
  Future<void> bindUid(String? uid);

  /// Last loaded / mutated list for the bound uid (sync filter).
  SoftDeleteList get snapshot;

  Set<String> get hiddenIds => snapshot.hiddenIds;

  Future<SoftDeleteList> read();

  Future<SoftDeleteList> hide(
    Iterable<String> cacheIds, {
    Duration grace = kSoftDeleteGrace,
    int? nowMs,
  });

  Future<SoftDeleteList> undo(Iterable<String> cacheIds);

  Future<SoftDeleteList> remove(Iterable<String> cacheIds);

  Future<void> clearBound();
}

class PrefsLibrarySoftDeleteStore implements LibrarySoftDeleteStore {
  PrefsLibrarySoftDeleteStore({SharedPreferences? prefs}) : _prefs = prefs;

  SharedPreferences? _prefs;
  String? _uid;
  SoftDeleteList _snapshot = SoftDeleteList();

  @override
  SoftDeleteList get snapshot => _snapshot;

  @override
  Set<String> get hiddenIds => _snapshot.hiddenIds;

  Future<SharedPreferences> _ready() async {
    return _prefs ??= await SharedPreferences.getInstance();
  }

  @override
  Future<void> bindUid(String? uid) async {
    _uid = (uid ?? '').trim().isEmpty ? null : uid!.trim();
    if (_uid == null) {
      _snapshot = SoftDeleteList();
      return;
    }
    await read();
  }

  String get _key => softDeletePrefsKey(_uid ?? '');

  Future<void> _persist(SoftDeleteList next) async {
    _snapshot = next;
    if (_uid == null || _uid!.isEmpty) return;
    final p = await _ready();
    if (next.isEmpty) {
      await p.remove(_key);
    } else {
      await p.setString(_key, next.encode());
    }
  }

  @override
  Future<SoftDeleteList> read() async {
    if (_uid == null || _uid!.isEmpty) {
      _snapshot = SoftDeleteList();
      return _snapshot;
    }
    final p = await _ready();
    _snapshot = SoftDeleteList.tryParse(p.getString(_key));
    return _snapshot;
  }

  @override
  Future<SoftDeleteList> hide(
    Iterable<String> cacheIds, {
    Duration grace = kSoftDeleteGrace,
    int? nowMs,
  }) async {
    if (_uid == null || _uid!.isEmpty) return SoftDeleteList();
    final now = nowMs ?? DateTime.now().millisecondsSinceEpoch;
    final purgeAt = now + grace.inMilliseconds;
    final ids = cacheIds
        .map((e) => e.trim())
        .where((e) => e.isNotEmpty)
        .toSet();
    if (ids.isEmpty) return read();
    final prev = await read();
    final kept = prev.entries.where((e) => !ids.contains(e.cacheId));
    final added = [
      for (final id in ids)
        SoftDeleteEntry(cacheId: id, purgeAtMs: purgeAt),
    ];
    final next = SoftDeleteList(entries: [...added, ...kept]);
    await _persist(next);
    return next;
  }

  @override
  Future<SoftDeleteList> undo(Iterable<String> cacheIds) async {
    return remove(cacheIds);
  }

  @override
  Future<SoftDeleteList> remove(Iterable<String> cacheIds) async {
    if (_uid == null || _uid!.isEmpty) return SoftDeleteList();
    final ids = cacheIds
        .map((e) => e.trim())
        .where((e) => e.isNotEmpty)
        .toSet();
    if (ids.isEmpty) return read();
    final prev = await read();
    final next = SoftDeleteList(
      entries: prev.entries.where((e) => !ids.contains(e.cacheId)).toList(),
    );
    await _persist(next);
    return next;
  }

  @override
  Future<void> clearBound() async {
    final p = await _ready();
    if (_uid != null && _uid!.isNotEmpty) {
      await p.remove(_key);
    }
    _uid = null;
    _snapshot = SoftDeleteList();
  }
}

class MemoryLibrarySoftDeleteStore implements LibrarySoftDeleteStore {
  String? _uid;
  final Map<String, SoftDeleteList> _byUid = {};
  SoftDeleteList _snapshot = SoftDeleteList();

  @override
  SoftDeleteList get snapshot => _snapshot;

  @override
  Set<String> get hiddenIds => _snapshot.hiddenIds;

  @override
  Future<void> bindUid(String? uid) async {
    _uid = (uid ?? '').trim().isEmpty ? null : uid!.trim();
    if (_uid == null) {
      _snapshot = SoftDeleteList();
      return;
    }
    _snapshot = _byUid[_uid!] ?? SoftDeleteList();
  }

  @override
  Future<SoftDeleteList> read() async {
    final u = _uid;
    if (u == null || u.isEmpty) {
      _snapshot = SoftDeleteList();
      return _snapshot;
    }
    _snapshot = _byUid[u] ?? SoftDeleteList();
    return _snapshot;
  }

  @override
  Future<SoftDeleteList> hide(
    Iterable<String> cacheIds, {
    Duration grace = kSoftDeleteGrace,
    int? nowMs,
  }) async {
    final u = _uid;
    if (u == null || u.isEmpty) return SoftDeleteList();
    final now = nowMs ?? DateTime.now().millisecondsSinceEpoch;
    final purgeAt = now + grace.inMilliseconds;
    final ids = cacheIds
        .map((e) => e.trim())
        .where((e) => e.isNotEmpty)
        .toSet();
    if (ids.isEmpty) return read();
    final prev = await read();
    final kept = prev.entries.where((e) => !ids.contains(e.cacheId));
    final added = [
      for (final id in ids)
        SoftDeleteEntry(cacheId: id, purgeAtMs: purgeAt),
    ];
    final next = SoftDeleteList(entries: [...added, ...kept]);
    _byUid[u] = next;
    _snapshot = next;
    return next;
  }

  @override
  Future<SoftDeleteList> undo(Iterable<String> cacheIds) async {
    return remove(cacheIds);
  }

  @override
  Future<SoftDeleteList> remove(Iterable<String> cacheIds) async {
    final u = _uid;
    if (u == null || u.isEmpty) return SoftDeleteList();
    final ids = cacheIds
        .map((e) => e.trim())
        .where((e) => e.isNotEmpty)
        .toSet();
    if (ids.isEmpty) return read();
    final prev = await read();
    final next = SoftDeleteList(
      entries: prev.entries.where((e) => !ids.contains(e.cacheId)).toList(),
    );
    _byUid[u] = next;
    _snapshot = next;
    return next;
  }

  @override
  Future<void> clearBound() async {
    final u = _uid;
    if (u != null) _byUid.remove(u);
    _uid = null;
    _snapshot = SoftDeleteList();
  }
}
