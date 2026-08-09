/// Persist upload draft metadata (+ optional local PDF path) for design/71.
library;

import 'dart:io';

import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'upload_draft_models.dart';

abstract class UploadDraftStore {
  Future<UploadDraft?> read();

  Future<void> write(UploadDraft draft);

  Future<void> clear();

  /// Write PDF bytes under app documents for auto-retry after kill.
  Future<String?> saveLocalPdf(String contentHash, List<int> bytes);

  Future<List<int>?> readLocalPdf(String path);
}

class PrefsUploadDraftStore implements UploadDraftStore {
  PrefsUploadDraftStore({SharedPreferences? prefs}) : _prefs = prefs;

  SharedPreferences? _prefs;

  Future<SharedPreferences> _ready() async {
    return _prefs ??= await SharedPreferences.getInstance();
  }

  @override
  Future<UploadDraft?> read() async {
    final p = await _ready();
    return UploadDraft.tryParse(p.getString(kUploadDraftPrefsKey));
  }

  @override
  Future<void> write(UploadDraft draft) async {
    final p = await _ready();
    await p.setString(kUploadDraftPrefsKey, draft.encode());
  }

  @override
  Future<void> clear() async {
    final p = await _ready();
    final prev = UploadDraft.tryParse(p.getString(kUploadDraftPrefsKey));
    await p.remove(kUploadDraftPrefsKey);
    // WHY: logout / success must not leave another account’s PDF on disk.
    if (prev != null && prev.localPath.isNotEmpty) {
      try {
        final f = File(prev.localPath);
        if (await f.exists()) await f.delete();
      } catch (_) {}
    }
  }

  @override
  Future<String?> saveLocalPdf(String contentHash, List<int> bytes) async {
    final hash = contentHash.trim().toLowerCase();
    if (!RegExp(r'^[a-f0-9]{64}$').hasMatch(hash) || bytes.isEmpty) {
      return null;
    }
    try {
      final root = await getApplicationDocumentsDirectory();
      final dir = Directory('${root.path}/ingest_drafts');
      if (!await dir.exists()) {
        await dir.create(recursive: true);
      }
      final path = '${dir.path}/$hash.pdf';
      await File(path).writeAsBytes(bytes, flush: true);
      return path;
    } catch (_) {
      return null;
    }
  }

  @override
  Future<List<int>?> readLocalPdf(String path) async {
    final p = path.trim();
    if (p.isEmpty) return null;
    // EDGE: only our app documents ingest_drafts tree.
    if (!p.contains('ingest_drafts')) return null;
    try {
      final f = File(p);
      if (!await f.exists()) return null;
      return await f.readAsBytes();
    } catch (_) {
      return null;
    }
  }
}

/// In-memory store for unit/widget tests (no disk).
class MemoryUploadDraftStore implements UploadDraftStore {
  UploadDraft? _draft;
  final Map<String, List<int>> _files = {};

  @override
  Future<UploadDraft?> read() async => _draft;

  @override
  Future<void> write(UploadDraft draft) async {
    _draft = draft;
  }

  @override
  Future<void> clear() async {
    _draft = null;
    _files.clear();
  }

  @override
  Future<String?> saveLocalPdf(String contentHash, List<int> bytes) async {
    final hash = contentHash.trim().toLowerCase();
    final path = 'memory/ingest_drafts/$hash.pdf';
    _files[path] = List<int>.from(bytes);
    return path;
  }

  @override
  Future<List<int>?> readLocalPdf(String path) async => _files[path];
}
