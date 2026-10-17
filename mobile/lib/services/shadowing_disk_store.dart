/// design/187 — on-device shadowing chunks / takes / voice (device SoT).
/// design/410 — reads and writes go through `disk_fs`, so the web keeps them in
/// browser storage too.
library;

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import 'disk_fs.dart';
import 'figure_disk_cache.dart';
import '../api/shadowing_chunk_plan.dart';
import 'local_disk.dart';

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
    if (!isBound || !localDiskAvailable) return null;
    final docs = await _docsRoot();
    return Directory(p.join(docs.path, kShadowingDiskStoreDirName, 'u', _uid));
  }

  /// The store's own folder: the app folder on a phone, browser storage on the web.
  Future<DiskDir?> _root() async {
    if (!isBound) return null;
    if (localDiskAvailable) {
      final docs = await _docsRoot();
      return DiskDir(p.join(docs.path, kShadowingDiskStoreDirName, 'u', _uid));
    }
    if (!browserDiskAvailable) return null;
    return DiskDir('/$kShadowingDiskStoreDirName/u/$_uid');
  }

  Future<DiskDir?> _dirOf(String cacheId) async {
    final root = await _root();
    final cid = figureCacheSafeToken(cacheId, maxLen: 32);
    if (root == null || cid.isEmpty) return null;
    return DiskDir(p.join(root.path, cid));
  }

  Future<List<String>> listChildDirNames() async {
    final root = await _root();
    if (root == null || !await root.exists()) return const [];
    final out = <String>[];
    await for (final e in root.list(followLinks: false)) {
      if (e is DiskDir) out.add(p.basename(e.path));
    }
    return out;
  }

  Future<Directory?> paperDir(String cacheId) async {
    final root = await uidRoot();
    final cid = figureCacheSafeToken(cacheId, maxLen: 32);
    if (root == null || cid.isEmpty) return null;
    return Directory(p.join(root.path, cid));
  }

  Future<DiskFile?> _chunkPlanFile(String cacheId) async {
    final dir = await _dirOf(cacheId);
    if (dir == null) return null;
    return DiskFile(p.join(dir.path, 'chunks.json'));
  }

  Future<DiskFile?> _takesFile(String cacheId) async {
    final dir = await _dirOf(cacheId);
    if (dir == null) return null;
    return DiskFile(p.join(dir.path, 'takes.json'));
  }

  Future<DiskDir?> _voiceDir(String cacheId) async {
    final dir = await _dirOf(cacheId);
    if (dir == null) return null;
    return DiskDir(p.join(dir.path, 'voice'));
  }

  Future<void> _atomicWriteBytes(DiskFile dest, List<int> bytes) async {
    final parent = dest.parent;
    if (!await parent.exists()) {
      await parent.create(recursive: true);
    }
    final part = DiskFile('${dest.path}.part');
    final bak = DiskFile('${dest.path}.bak');
    await part.writeAsBytes(bytes, flush: true);
    if (await bak.exists()) {
      await bak.delete();
    }
    // Keep the previous file until the new one is in place. Do not delete first.
    if (await dest.exists()) {
      await dest.rename(bak.path);
    }
    try {
      await part.rename(dest.path);
    } catch (_) {
      if (!await dest.exists() && await bak.exists()) {
        await bak.rename(dest.path);
      }
      rethrow;
    }
  }

  Future<void> _discardBak(DiskFile dest) async {
    final bak = DiskFile('${dest.path}.bak');
    if (await bak.exists()) {
      await bak.delete();
    }
  }

  Future<void> _restoreBak(DiskFile dest) async {
    final bak = DiskFile('${dest.path}.bak');
    if (!await bak.exists()) return;
    if (await dest.exists()) {
      await dest.delete();
    }
    await bak.rename(dest.path);
  }

  Future<void> _atomicWriteString(DiskFile dest, String text) async {
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
      final loaded = await loadChunkPlanJson(cacheId);
      if (!shadowingPlanRetainsSentences(loaded, plan)) {
        await _restoreBak(f);
        return false;
      }
      await _discardBak(f);
      return true;
    } catch (_) {
      try {
        await _restoreBak(f);
      } catch (_) {}
      return false;
    }
  }

  Future<Map<String, dynamic>?> _readPlanFile(DiskFile f) async {
    if (!await f.exists()) return null;
    try {
      final raw = jsonDecode(await f.readAsString());
      if (raw is Map<String, dynamic>) return raw;
      if (raw is Map) return Map<String, dynamic>.from(raw);
    } catch (_) {}
    return null;
  }

  Future<Map<String, dynamic>?> loadChunkPlanJson(String cacheId) async {
    final f = await _chunkPlanFile(cacheId);
    if (f == null) return null;
    return await _readPlanFile(f) ??
        await _readPlanFile(DiskFile('${f.path}.bak'));
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
      await _atomicWriteBytes(DiskFile(path), bytes);
      return true;
    } catch (_) {
      return false;
    }
  }

  /// design/410 — voice file names (`<safe>.bin`) held for one paper.
  Future<List<String>> listVoiceNames(String cacheId) async {
    final voice = await _voiceDir(cacheId);
    if (voice == null || !await voice.exists()) return const [];
    final out = <String>[];
    await for (final ent in voice.list(followLinks: false)) {
      if (ent is! DiskFile) continue;
      final name = p.basename(ent.path);
      if (name.endsWith('.bin')) out.add(name);
    }
    out.sort();
    return out;
  }

  /// design/410 — fold another device's shadowing files for one paper in.
  ///
  /// Nothing held here is replaced: a voice file is written only when missing, the
  /// chunk plan only when there is none, and a take slot only when it is empty here.
  /// Returns how many files changed.
  Future<int> mergePackFiles(
    String cacheId,
    Map<String, Uint8List> files,
  ) async {
    final dir = await _dirOf(cacheId);
    if (dir == null) return 0;
    var n = 0;
    for (final e in files.entries) {
      if (!e.key.startsWith('shadowing/voice/')) continue;
      final name = e.key.substring('shadowing/voice/'.length);
      if (name.isEmpty || name.contains('/') || !name.endsWith('.bin')) {
        continue;
      }
      if (e.value.isEmpty) continue;
      final dest = DiskFile(p.join(dir.path, 'voice', name));
      if (await dest.exists()) continue;
      try {
        await _atomicWriteBytes(dest, e.value);
        n += 1;
      } catch (_) {}
    }
    final plan = files['shadowing/chunks.json'];
    if (plan != null && plan.isNotEmpty && await loadChunkPlanJson(cacheId) == null) {
      final f = await _chunkPlanFile(cacheId);
      if (f != null) {
        try {
          await _atomicWriteBytes(f, plan);
          n += 1;
        } catch (_) {}
      }
    }
    final theirs = files['shadowing/takes.json'];
    if (theirs != null && theirs.isNotEmpty) {
      Map<String, dynamic>? incoming;
      try {
        final raw = jsonDecode(utf8.decode(theirs));
        if (raw is Map) incoming = Map<String, dynamic>.from(raw);
      } catch (_) {}
      if (incoming != null) {
        final mine = await loadTakesJson(cacheId);
        final merged = mergeShadowingTakes(mine, incoming, cacheId: cacheId);
        if (jsonEncode(merged) != jsonEncode(mine) &&
            await writeTakesJson(cacheId, merged)) {
          n += 1;
        }
      }
    }
    return n;
  }

  /// Pack-relative paths for design/186 phase E / design/187 E.
  Future<Map<String, Uint8List>> listPackFiles(String cacheId) async {
    final out = <String, Uint8List>{};
    final dir = await _dirOf(cacheId);
    if (dir == null || !await dir.exists()) return out;

    Future<void> maybeAdd(String absRel, String packRel) async {
      final f = DiskFile(p.join(dir.path, absRel));
      if (!await f.exists()) return;
      try {
        final bytes = await f.readAsBytes();
        if (bytes.isEmpty) return;
        out[packRel] = Uint8List.fromList(bytes);
      } catch (_) {}
    }

    await maybeAdd('chunks.json', 'shadowing/chunks.json');
    await maybeAdd('takes.json', 'shadowing/takes.json');
    final voice = DiskDir(p.join(dir.path, 'voice'));
    if (await voice.exists()) {
      await for (final ent in voice.list(followLinks: false)) {
        if (ent is! DiskFile) continue;
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
      final dir = await _dirOf(cacheId);
      if (dir == null) continue;
      final dest = DiskFile(p.join(dir.path, rest));
      try {
        await _atomicWriteBytes(dest, e.value);
        n += 1;
      } catch (_) {}
    }
    return n;
  }

  Future<void> purge(String cacheId) async {
    final dir = await _dirOf(cacheId);
    if (dir == null || !await dir.exists()) return;
    try {
      await dir.delete(recursive: true);
    } catch (_) {}
  }
}

bool _takeSlotFilled(Object? slot) {
  if (slot is! Map) return false;
  final status = '${slot['status'] ?? ''}'.trim();
  final key = '${slot['blob_key'] ?? ''}'.trim();
  return key.isNotEmpty || (status.isNotEmpty && status != 'empty');
}

/// design/410 — union of two takes documents (`sentences.<id>.chunks[i]`).
///
/// A slot filled here stays; an empty or missing slot takes the other device's.
Map<String, dynamic> mergeShadowingTakes(
  Map<String, dynamic>? mine,
  Map<String, dynamic> theirs, {
  required String cacheId,
}) {
  final out = Map<String, dynamic>.from(
    mine ?? {'version': 1, 'cache_id': cacheId, 'sentences': <String, dynamic>{}},
  );
  final sentences = Map<String, dynamic>.from(
    (out['sentences'] is Map) ? out['sentences'] as Map : const {},
  );
  final their = (theirs['sentences'] is Map) ? theirs['sentences'] as Map : const {};
  for (final e in their.entries) {
    final sid = '${e.key}';
    if (e.value is! Map) continue;
    final theirRow = Map<String, dynamic>.from(e.value as Map);
    final row = Map<String, dynamic>.from(
      (sentences[sid] is Map) ? sentences[sid] as Map : const {},
    );
    final chunks = List<dynamic>.from(
      (row['chunks'] is List) ? row['chunks'] as List : const [],
    );
    final theirChunks =
        (theirRow['chunks'] is List) ? theirRow['chunks'] as List : const [];
    for (var i = 0; i < theirChunks.length; i++) {
      while (chunks.length <= i) {
        chunks.add({'status': 'empty', 'blob_key': null, 'mime': null});
      }
      if (!_takeSlotFilled(chunks[i]) && _takeSlotFilled(theirChunks[i])) {
        chunks[i] = Map<String, dynamic>.from(theirChunks[i] as Map);
      }
    }
    row['chunks'] = chunks;
    sentences[sid] = row;
  }
  out['sentences'] = sentences;
  out['cache_id'] = cacheId;
  return out;
}
