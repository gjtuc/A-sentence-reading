/// design/187 — on-device shadowing chunks / takes / voice (device SoT).
library;

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import 'figure_disk_cache.dart';

const String kShadowingDiskStoreDirName = 'asr_shadowing';

/// Persist chunk plans, takes JSON, and voice blobs under app documents.
class ShadowingDiskStore {
  ShadowingDiskStore({this.rootResolver});

  /// Test hook — default [getApplicationDocumentsDirectory].
  final Future<Directory> Function()? rootResolver;

  String _uid = '';

  bool get isBound => _uid.isNotEmpty;

  void bindUid(String? uid) {
    _uid = figureCacheSafeToken(uid ?? '', maxLen: 80);
  }

  Future<Directory> _docsRoot() async {
    if (rootResolver != null) return rootResolver!();
    return getApplicationDocumentsDirectory();
  }

  Future<Directory?> uidRoot() async {
    if (!isBound) return null;
    final docs = await _docsRoot();
    return Directory(p.join(docs.path, kShadowingDiskStoreDirName, 'u', _uid));
  }

  Future<Directory?> paperDir(String cacheId) async {
    final root = await uidRoot();
    final cid = figureCacheSafeToken(cacheId, maxLen: 32);
    if (root == null || cid.isEmpty) return null;
    return Directory(p.join(root.path, cid));
  }

  Future<File?> _chunkPlanFile(String cacheId) async {
    final dir = await paperDir(cacheId);
    if (dir == null) return null;
    return File(p.join(dir.path, 'chunks.json'));
  }

  Future<File?> _takesFile(String cacheId) async {
    final dir = await paperDir(cacheId);
    if (dir == null) return null;
    return File(p.join(dir.path, 'takes.json'));
  }

  Future<Directory?> _voiceDir(String cacheId) async {
    final dir = await paperDir(cacheId);
    if (dir == null) return null;
    return Directory(p.join(dir.path, 'voice'));
  }

  Future<void> _atomicWriteBytes(File dest, List<int> bytes) async {
    final parent = dest.parent;
    if (!await parent.exists()) {
      await parent.create(recursive: true);
    }
    final part = File('${dest.path}.part');
    await part.writeAsBytes(bytes, flush: true);
    if (await dest.exists()) {
      await dest.delete();
    }
    await part.rename(dest.path);
  }

  Future<void> _atomicWriteString(File dest, String text) async {
    await _atomicWriteBytes(dest, utf8.encode(text));
  }

  Future<bool> writeChunkPlanJson(
    String cacheId,
    Map<String, dynamic> plan,
  ) async {
    final f = await _chunkPlanFile(cacheId);
    if (f == null) return false;
    try {
      await _atomicWriteString(f, jsonEncode(plan));
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<Map<String, dynamic>?> loadChunkPlanJson(String cacheId) async {
    final f = await _chunkPlanFile(cacheId);
    if (f == null || !await f.exists()) return null;
    try {
      final raw = jsonDecode(await f.readAsString());
      if (raw is Map<String, dynamic>) return raw;
      if (raw is Map) return Map<String, dynamic>.from(raw);
    } catch (_) {}
    return null;
  }

  Future<bool> writeTakesJson(
    String cacheId,
    Map<String, dynamic> takes,
  ) async {
    final f = await _takesFile(cacheId);
    if (f == null) return false;
    try {
      await _atomicWriteString(f, jsonEncode(takes));
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<Map<String, dynamic>?> loadTakesJson(String cacheId) async {
    final f = await _takesFile(cacheId);
    if (f == null || !await f.exists()) return null;
    try {
      final raw = jsonDecode(await f.readAsString());
      if (raw is Map<String, dynamic>) return raw;
      if (raw is Map) return Map<String, dynamic>.from(raw);
    } catch (_) {}
    return null;
  }

  String _voiceSafeName(String blobKey) {
    final safe = figureCacheSafeToken(blobKey, maxLen: 120);
    return safe.isEmpty ? 'voice' : safe;
  }

  Future<String?> voiceFilePath(String cacheId, String blobKey) async {
    final dir = await _voiceDir(cacheId);
    final name = _voiceSafeName(blobKey);
    if (dir == null || name.isEmpty) return null;
    return p.join(dir.path, '$name.bin');
  }

  Future<bool> writeVoiceBytes(
    String cacheId,
    String blobKey,
    List<int> bytes,
  ) async {
    if (bytes.isEmpty) return false;
    final path = await voiceFilePath(cacheId, blobKey);
    if (path == null) return false;
    try {
      await _atomicWriteBytes(File(path), bytes);
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Pack-relative paths for design/186 phase E / design/187 E.
  Future<Map<String, Uint8List>> listPackFiles(String cacheId) async {
    final out = <String, Uint8List>{};
    final dir = await paperDir(cacheId);
    if (dir == null || !await dir.exists()) return out;

    Future<void> maybeAdd(String absRel, String packRel) async {
      final f = File(p.join(dir.path, absRel));
      if (!await f.exists()) return;
      try {
        final bytes = await f.readAsBytes();
        if (bytes.isEmpty) return;
        out[packRel] = Uint8List.fromList(bytes);
      } catch (_) {}
    }

    await maybeAdd('chunks.json', 'shadowing/chunks.json');
    await maybeAdd('takes.json', 'shadowing/takes.json');
    final voice = Directory(p.join(dir.path, 'voice'));
    if (await voice.exists()) {
      await for (final ent in voice.list(followLinks: false)) {
        if (ent is! File) continue;
        final name = p.basename(ent.path);
        if (!name.endsWith('.bin')) continue;
        try {
          final bytes = await ent.readAsBytes();
          if (bytes.isEmpty) continue;
          out['shadowing/voice/$name'] = Uint8List.fromList(bytes);
        } catch (_) {}
      }
    }
    return out;
  }

  /// Restore pack keys under `shadowing/` into the paper folder.
  Future<int> applyPackFiles(
    String cacheId,
    Map<String, Uint8List> files,
  ) async {
    var n = 0;
    for (final e in files.entries) {
      final rel = e.key.trim();
      if (!rel.startsWith('shadowing/')) continue;
      final rest = rel.substring('shadowing/'.length);
      if (rest.isEmpty || rest.contains('..')) continue;
      final dir = await paperDir(cacheId);
      if (dir == null) continue;
      final dest = File(p.join(dir.path, rest));
      try {
        await _atomicWriteBytes(dest, e.value);
        n += 1;
      } catch (_) {}
    }
    return n;
  }

  Future<void> purge(String cacheId) async {
    final dir = await paperDir(cacheId);
    if (dir == null || !await dir.exists()) return;
    try {
      await dir.delete(recursive: true);
    } catch (_) {}
  }
}
