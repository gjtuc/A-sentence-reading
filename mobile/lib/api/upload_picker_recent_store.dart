/// Persist recent pick metadata (design/223).
library;

import 'package:shared_preferences/shared_preferences.dart';

import 'upload_picker_recent_models.dart';

abstract class UploadPickerRecentStore {
  Future<void> bindUid(String? uid);

  Future<PickerRecentList> read();

  Future<void> remember({
    required String contentHash,
    required String displayName,
    String label = '',
    String source = 'saf',
  });

  Future<void> clearBound();
}

class PrefsUploadPickerRecentStore implements UploadPickerRecentStore {
  PrefsUploadPickerRecentStore({SharedPreferences? prefs}) : _prefs = prefs;

  SharedPreferences? _prefs;
  String? _uid;

  Future<SharedPreferences> _ready() async {
    return _prefs ??= await SharedPreferences.getInstance();
  }

  @override
  Future<void> bindUid(String? uid) async {
    _uid = (uid ?? '').trim().isEmpty ? null : uid!.trim();
  }

  String get _key => pickerRecentPrefsKey(_uid ?? '');

  @override
  Future<PickerRecentList> read() async {
    if (_uid == null || _uid!.isEmpty) return PickerRecentList();
    final p = await _ready();
    return PickerRecentList.tryParse(p.getString(_key));
  }

  @override
  Future<void> remember({
    required String contentHash,
    required String displayName,
    String label = '',
    String source = 'saf',
  }) async {
    if (_uid == null || _uid!.isEmpty) return;
    final hash = contentHash.trim().toLowerCase();
    final name = displayName.trim();
    if (hash.length != 64 || name.isEmpty) return;
    final prev = await read();
    final next = <PickerRecentItem>[
      PickerRecentItem(
        contentHash: hash,
        displayName: name,
        label: label.trim(),
        uploadedAtMs: DateTime.now().millisecondsSinceEpoch,
        source: source,
      ),
      ...prev.items.where((e) => e.contentHash != hash),
    ];
    if (next.length > kPickerRecentMaxItems) {
      next.removeRange(kPickerRecentMaxItems, next.length);
    }
    final p = await _ready();
    await p.setString(_key, PickerRecentList(items: next).encode());
  }

  @override
  Future<void> clearBound() async {
    final p = await _ready();
    if (_uid != null && _uid!.isNotEmpty) {
      await p.remove(_key);
    }
    _uid = null;
  }
}

class MemoryUploadPickerRecentStore implements UploadPickerRecentStore {
  String? _uid;
  final Map<String, PickerRecentList> _byUid = {};

  @override
  Future<void> bindUid(String? uid) async {
    _uid = (uid ?? '').trim().isEmpty ? null : uid!.trim();
  }

  @override
  Future<PickerRecentList> read() async {
    final u = _uid;
    if (u == null || u.isEmpty) return PickerRecentList();
    return _byUid[u] ?? PickerRecentList();
  }

  @override
  Future<void> remember({
    required String contentHash,
    required String displayName,
    String label = '',
    String source = 'saf',
  }) async {
    final u = _uid;
    if (u == null || u.isEmpty) return;
    final hash = contentHash.trim().toLowerCase();
    final name = displayName.trim();
    if (hash.length != 64 || name.isEmpty) return;
    final prev = await read();
    final next = <PickerRecentItem>[
      PickerRecentItem(
        contentHash: hash,
        displayName: name,
        label: label,
        uploadedAtMs: DateTime.now().millisecondsSinceEpoch,
        source: source,
      ),
      ...prev.items.where((e) => e.contentHash != hash),
    ];
    _byUid[u] = PickerRecentList(
      items: next.take(kPickerRecentMaxItems).toList(),
    );
  }

  @override
  Future<void> clearBound() async {
    final u = _uid;
    if (u != null) _byUid.remove(u);
    _uid = null;
  }
}
