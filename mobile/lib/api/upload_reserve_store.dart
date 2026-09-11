/// Persist upload reservation queue + local PDFs (design/221).
library;

import 'dart:io';

import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'upload_reserve_models.dart';

abstract class UploadReserveStore {
  Future<UploadReserveQueue> read();

  Future<void> write(UploadReserveQueue queue);

  Future<void> clear();

  Future<String?> saveLocalPdf(String contentHash, List<int> bytes);

  Future<List<int>?> readLocalPdf(String path);

  Future<void> deleteLocalPdf(String path);
}

class PrefsUploadReserveStore implements UploadReserveStore {
  PrefsUploadReserveStore({SharedPreferences? prefs}) : _prefs = prefs;

  SharedPreferences? _prefs;

  Future<SharedPreferences> _ready() async {
    return _prefs ??= await SharedPreferences.getInstance();
  }

  @override
  Future<UploadReserveQueue> read() async {
    final p = await _ready();
    return UploadReserveQueue.tryParse(p.getString(kUploadReservePrefsKey));
  }

  @override
  Future<void> write(UploadReserveQueue queue) async {
    final p = await _ready();
    if (queue.isEmpty) {
      await p.remove(kUploadReservePrefsKey);
      return;
    }
    await p.setString(kUploadReservePrefsKey, queue.encode());
  }

  @override
  Future<void> clear() async {
    final prev = await read();
    final p = await _ready();
    await p.remove(kUploadReservePrefsKey);
    for (final item in prev.items) {
      await deleteLocalPdf(item.localPath);
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
      final dir = Directory('${root.path}/ingest_reserve');
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
    // EDGE: only our app documents ingest_reserve tree (never ingest_drafts).
    if (!p.contains('ingest_reserve')) return null;
    try {
      final f = File(p);
      if (!await f.exists()) return null;
      return await f.readAsBytes();
    } catch (_) {
      return null;
    }
  }

  @override
  Future<void> deleteLocalPdf(String path) async {
    final p = path.trim();
    if (p.isEmpty || !p.contains('ingest_reserve')) return;
    try {
      final f = File(p);
      if (await f.exists()) await f.delete();
    } catch (_) {}
  }
}

/// In-memory store for unit tests (no disk).
class MemoryUploadReserveStore implements UploadReserveStore {
  UploadReserveQueue _queue = UploadReserveQueue();
  final Map<String, List<int>> _files = {};

  @override
  Future<UploadReserveQueue> read() async => _queue;

  @override
  Future<void> write(UploadReserveQueue queue) async {
    _queue = UploadReserveQueue(items: queue.items);
  }

  @override
  Future<void> clear() async {
    _queue = UploadReserveQueue();
    _files.clear();
  }

  @override
  Future<String?> saveLocalPdf(String contentHash, List<int> bytes) async {
    final hash = contentHash.trim().toLowerCase();
    final path = 'memory/ingest_reserve/$hash.pdf';
    _files[path] = List<int>.from(bytes);
    return path;
  }

  @override
  Future<List<int>?> readLocalPdf(String path) async => _files[path];

  @override
  Future<void> deleteLocalPdf(String path) async {
    _files.remove(path);
  }
}
