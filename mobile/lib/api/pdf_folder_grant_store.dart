/// design/226 — persist folder grant (uid-scoped).
library;

import 'package:shared_preferences/shared_preferences.dart';

import 'pdf_folder_grant_models.dart';

abstract class PdfFolderGrantStore {
  Future<void> bindUid(String? uid);

  Future<PdfFolderGrant?> read();

  Future<void> write(PdfFolderGrant grant);

  Future<void> clearBound();
}

class PrefsPdfFolderGrantStore implements PdfFolderGrantStore {
  PrefsPdfFolderGrantStore({SharedPreferences? prefs}) : _prefs = prefs;

  SharedPreferences? _prefs;
  String? _uid;

  Future<SharedPreferences> _ready() async {
    return _prefs ??= await SharedPreferences.getInstance();
  }

  @override
  Future<void> bindUid(String? uid) async {
    _uid = (uid ?? '').trim().isEmpty ? null : uid!.trim();
  }

  String get _key => pdfFolderGrantPrefsKey(_uid ?? '');

  @override
  Future<PdfFolderGrant?> read() async {
    if (_uid == null || _uid!.isEmpty) return null;
    final p = await _ready();
    return PdfFolderGrant.tryParse(p.getString(_key));
  }

  @override
  Future<void> write(PdfFolderGrant grant) async {
    if (_uid == null || _uid!.isEmpty) return;
    if (grant.treeUri.trim().isEmpty) return;
    final p = await _ready();
    await p.setString(_key, grant.encode());
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

class MemoryPdfFolderGrantStore implements PdfFolderGrantStore {
  String? _uid;
  final Map<String, PdfFolderGrant> _byUid = {};

  @override
  Future<void> bindUid(String? uid) async {
    _uid = (uid ?? '').trim().isEmpty ? null : uid!.trim();
  }

  @override
  Future<PdfFolderGrant?> read() async {
    final u = _uid;
    if (u == null || u.isEmpty) return null;
    return _byUid[u];
  }

  @override
  Future<void> write(PdfFolderGrant grant) async {
    final u = _uid;
    if (u == null || u.isEmpty) return;
    _byUid[u] = grant;
  }

  @override
  Future<void> clearBound() async {
    final u = _uid;
    if (u != null) _byUid.remove(u);
    _uid = null;
  }
}
