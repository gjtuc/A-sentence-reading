/// design/171 — on-device permanent figure/table PNG cache (per uid · cache_id).
///
/// Survives process kill; purged on library paper delete. Not temp dir.
library;

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import '../api/reading_models.dart';

const int kFigureDiskMaxBytes = 8 * 1024 * 1024;

/// Sanitize uid / cache_id / figure id for filesystem paths.
String figureCacheSafeToken(String raw, {int maxLen = 64}) {
  final t = raw.trim();
  if (t.isEmpty) return '';
  final buf = StringBuffer();
  for (final cu in t.codeUnits) {
    final ch = String.fromCharCode(cu);
    if (RegExp(r'[a-zA-Z0-9_-]').hasMatch(ch)) {
      buf.write(ch);
    } else {
      buf.write('_');
    }
    if (buf.length >= maxLen) break;
  }
  return buf.toString();
}

String figureDiskSha16(Uint8List bytes) {
  if (bytes.isEmpty) return '';
  return sha256.convert(bytes).toString().substring(0, 16);
}

String figureDataUrlFromBytes(Uint8List bytes, {String mime = 'image/png'}) {
  final m = mime.trim().isEmpty ? 'image/png' : mime.trim();
  return 'data:$m;base64,${base64Encode(bytes)}';
}

Uint8List? figureBytesFromDataUrl(String? src) {
  final decoded = decodeRasterDataUrl(src);
  return decoded?.bytes;
}

class FigureDiskManifest {
  FigureDiskManifest({
    required this.cacheId,
    required this.uid,
    this.contentHash = '',
    this.updatedAt = '',
    Map<String, FigureDiskEntry>? figures,
    this.version = 1,
  }) : figures = figures ?? {};

  final int version;
  final String cacheId;
  final String uid;
  String contentHash;
  String updatedAt;
  final Map<String, FigureDiskEntry> figures;

  Map<String, dynamic> toJson() => {
        'version': version,
        'cache_id': cacheId,
        'uid': uid,
        'content_hash': contentHash,
        'updated_at': updatedAt,
        'figures': {
          for (final e in figures.entries) e.key: e.value.toJson(),
        },
      };

  static FigureDiskManifest? fromJson(Map<String, dynamic>? json) {
    if (json == null) return null;
    final cid = '${json['cache_id'] ?? ''}'.trim();
    if (cid.isEmpty) return null;
    final figs = <String, FigureDiskEntry>{};
    final raw = json['figures'];
    if (raw is Map) {
      for (final e in raw.entries) {
        final id = '${e.key}'.trim();
        if (id.isEmpty) continue;
        if (e.value is Map) {
          final row = FigureDiskEntry.fromJson(
            Map<String, dynamic>.from(e.value as Map),
          );
          if (row != null) figs[id] = row;
        }
      }
    }
    return FigureDiskManifest(
      version: (json['version'] as num?)?.toInt() ?? 1,
      cacheId: cid,
      uid: '${json['uid'] ?? ''}'.trim(),
      contentHash: '${json['content_hash'] ?? ''}'.trim(),
      updatedAt: '${json['updated_at'] ?? ''}'.trim(),
      figures: figs,
    );
  }
}

class FigureDiskEntry {
  const FigureDiskEntry({
    required this.bytes,
    required this.sha16,
    required this.savedAt,
  });

  final int bytes;
  final String sha16;
  final String savedAt;

  Map<String, dynamic> toJson() => {
        'bytes': bytes,
        'sha16': sha16,
        'saved_at': savedAt,
      };

  static FigureDiskEntry? fromJson(Map<String, dynamic>? json) {
    if (json == null) return null;
    final n = (json['bytes'] as num?)?.toInt() ?? 0;
    if (n < 1) return null;
    return FigureDiskEntry(
      bytes: n,
      sha16: '${json['sha16'] ?? ''}'.trim(),
      savedAt: '${json['saved_at'] ?? ''}'.trim(),
    );
  }
}

/// Documents-dir PNG cache: `asr_figure_cache/u/{uid}/{cache_id}/`.
class FigureDiskCache {
  FigureDiskCache({Future<Directory> Function()? rootResolver})
      : _rootResolver = rootResolver ?? _defaultRoot;

  final Future<Directory> Function() _rootResolver;
  String _uid = '';

  static const cacheDirName = 'asr_figure_cache';
  static const maxFigureBytes = kFigureDiskMaxBytes;

  static Future<Directory> _defaultRoot() => getApplicationDocumentsDirectory();

  String get uid => _uid;

  void bindUid(String? uid) {
    _uid = figureCacheSafeToken(uid ?? '', maxLen: 80);
  }

  bool get isBound => _uid.isNotEmpty;

  Future<Directory> _uidRoot() async {
    final docs = await _rootResolver();
    final dir = Directory(p.join(docs.path, cacheDirName, 'u', _uid));
    if (!await dir.exists()) {
      await dir.create(recursive: true);
    }
    return dir;
  }

  Future<Directory?> paperDir(String cacheId) async {
    if (!isBound) return null;
    final id = figureCacheSafeToken(cacheId, maxLen: 32);
    if (id.isEmpty) return null;
    return Directory(p.join((await _uidRoot()).path, id));
  }

  Future<File?> _manifestFile(String cacheId) async {
    final dir = await paperDir(cacheId);
    if (dir == null) return null;
    return File(p.join(dir.path, 'manifest.json'));
  }

  Future<File?> _pngFile(String cacheId, String figureId) async {
    final dir = await paperDir(cacheId);
    if (dir == null) return null;
    final fid = figureCacheSafeToken(figureId, maxLen: 64);
    if (fid.isEmpty) return null;
    return File(p.join(dir.path, '$fid.png'));
  }

  Future<FigureDiskManifest?> loadManifest(String cacheId) async {
    if (!isBound) return null;
    final f = await _manifestFile(cacheId);
    if (f == null || !await f.exists()) return null;
    try {
      final raw = jsonDecode(await f.readAsString());
      if (raw is! Map) return null;
      return FigureDiskManifest.fromJson(Map<String, dynamic>.from(raw));
    } catch (_) {
      return null;
    }
  }

  Future<void> _saveManifest(FigureDiskManifest m) async {
    final f = await _manifestFile(m.cacheId);
    final dir = await paperDir(m.cacheId);
    if (f == null || dir == null) return;
    if (!await dir.exists()) {
      await dir.create(recursive: true);
    }
    m.updatedAt = DateTime.now().toUtc().toIso8601String();
    final tmp = File('${f.path}.part');
    await tmp.writeAsString(jsonEncode(m.toJson()), flush: true);
    if (await f.exists()) {
      await f.delete();
    }
    await tmp.rename(f.path);
  }

  /// Wipe paper dir when [contentHash] disagrees with manifest (reanalyze).
  Future<bool> ensureContentHash(String cacheId, String contentHash) async {
    final ch = contentHash.trim().toLowerCase();
    if (ch.isEmpty) return false;
    final m = await loadManifest(cacheId);
    if (m == null) return false;
    final prev = m.contentHash.trim().toLowerCase();
    if (prev.isEmpty || prev == ch) {
      if (prev.isEmpty) {
        m.contentHash = ch;
        await _saveManifest(m);
      }
      return false;
    }
    await purge(cacheId);
    return true;
  }

  Future<bool> has(String cacheId, String figureId) async {
    final bytes = await readBytes(cacheId, figureId);
    return bytes != null && bytes.isNotEmpty;
  }

  Future<Uint8List?> readBytes(String cacheId, String figureId) async {
    if (!isBound) return null;
    final f = await _pngFile(cacheId, figureId);
    if (f == null || !await f.exists()) return null;
    try {
      final bytes = await f.readAsBytes();
      if (bytes.isEmpty || bytes.length > maxFigureBytes) return null;
      final m = await loadManifest(cacheId);
      final fid = figureCacheSafeToken(figureId, maxLen: 64);
      final entry = m?.figures[fid];
      if (entry != null && entry.bytes > 0 && entry.bytes != bytes.length) {
        // EDGE: partial / corrupt vs manifest — treat as miss.
        return null;
      }
      return Uint8List.fromList(bytes);
    } catch (_) {
      return null;
    }
  }

  Future<String?> readDataUrl(String cacheId, String figureId) async {
    final bytes = await readBytes(cacheId, figureId);
    if (bytes == null || bytes.isEmpty) return null;
    return figureDataUrlFromBytes(bytes);
  }

  Future<bool> writeBytes(
    String cacheId, {
    required String figureId,
    required Uint8List bytes,
    String contentHash = '',
  }) async {
    if (!isBound) return false;
    if (bytes.isEmpty || bytes.length > maxFigureBytes) return false;
    final fid = figureCacheSafeToken(figureId, maxLen: 64);
    final cid = figureCacheSafeToken(cacheId, maxLen: 32);
    if (fid.isEmpty || cid.isEmpty) return false;
    final dir = await paperDir(cacheId);
    final f = await _pngFile(cacheId, figureId);
    if (dir == null || f == null) return false;
    try {
      if (!await dir.exists()) {
        await dir.create(recursive: true);
      }
      final part = File('${f.path}.part');
      await part.writeAsBytes(bytes, flush: true);
      if (await f.exists()) {
        await f.delete();
      }
      await part.rename(f.path);

      var m = await loadManifest(cacheId);
      m ??= FigureDiskManifest(cacheId: cid, uid: _uid);
      final ch = contentHash.trim().toLowerCase();
      if (ch.isNotEmpty) m.contentHash = ch;
      m.figures[fid] = FigureDiskEntry(
        bytes: bytes.length,
        sha16: figureDiskSha16(bytes),
        savedAt: DateTime.now().toUtc().toIso8601String(),
      );
      await _saveManifest(m);
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<bool> writeDataUrl(
    String cacheId, {
    required String figureId,
    required String imageSrc,
    String contentHash = '',
  }) async {
    final bytes = figureBytesFromDataUrl(imageSrc);
    if (bytes == null || bytes.isEmpty) return false;
    return writeBytes(
      cacheId,
      figureId: figureId,
      bytes: bytes,
      contentHash: contentHash,
    );
  }

  /// How many of [expectedIds] exist as valid PNG files.
  Future<int> filledCount(
    String cacheId,
    Iterable<String> expectedIds,
  ) async {
    var n = 0;
    for (final id in expectedIds) {
      if (await has(cacheId, id)) n++;
    }
    return n;
  }

  Future<void> purge(String cacheId) async {
    final dir = await paperDir(cacheId);
    if (dir == null) return;
    try {
      if (await dir.exists()) {
        await dir.delete(recursive: true);
      }
    } catch (_) {
      // Best-effort.
    }
  }

  /// Delete all papers for the bound uid (logout optional aggressive wipe).
  Future<void> purgeAllForUid() async {
    if (!isBound) return;
    try {
      final root = await _uidRoot();
      if (await root.exists()) {
        await root.delete(recursive: true);
      }
    } catch (_) {
      // Best-effort.
    }
  }
}
