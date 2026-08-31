/// design/163-E — Figure edit용 로컬 원본 스태시 (ingest_drafts와 분리).
library;

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

class PaperStashMeta {
  const PaperStashMeta({
    required this.cacheId,
    required this.contentHash,
    required this.sourceFilename,
    required this.sourceBytes,
    required this.savedAt,
    this.invalidatedAt,
    this.stashVersion = 1,
  });

  final String cacheId;
  final String contentHash;
  final String sourceFilename;
  final int sourceBytes;
  final DateTime savedAt;
  final DateTime? invalidatedAt;
  final int stashVersion;

  bool get isValid =>
      cacheId.isNotEmpty && sourceFilename.isNotEmpty && sourceBytes > 0;

  bool get needsSourceRefresh => invalidatedAt != null;

  Map<String, dynamic> toJson() => {
        'cache_id': cacheId,
        'content_hash': contentHash,
        'source_filename': sourceFilename,
        'source_bytes': sourceBytes,
        'saved_at': savedAt.toUtc().toIso8601String(),
        'invalidated_at': invalidatedAt?.toUtc().toIso8601String(),
        'stash_version': stashVersion,
      };

  static PaperStashMeta? fromJson(Map<String, dynamic>? json) {
    if (json == null) return null;
    final cid = '${json['cache_id'] ?? ''}'.trim();
    if (cid.isEmpty) return null;
    final savedRaw = '${json['saved_at'] ?? ''}'.trim();
    final savedAt = DateTime.tryParse(savedRaw) ?? DateTime.now().toUtc();
    DateTime? invalidated;
    final invRaw = '${json['invalidated_at'] ?? ''}'.trim();
    if (invRaw.isNotEmpty) {
      invalidated = DateTime.tryParse(invRaw);
    }
    return PaperStashMeta(
      cacheId: cid,
      contentHash: '${json['content_hash'] ?? ''}'.trim(),
      sourceFilename: '${json['source_filename'] ?? 'source.pdf'}'.trim(),
      sourceBytes: (json['source_bytes'] as num?)?.toInt() ?? 0,
      savedAt: savedAt,
      invalidatedAt: invalidated,
      stashVersion: (json['stash_version'] as num?)?.toInt() ?? 1,
    );
  }
}

class PaperStashException implements Exception {
  PaperStashException(this.code, [this.message = '']);

  final String code;
  final String message;

  @override
  String toString() => 'PaperStashException($code): $message';
}

class PaperEditStash {
  PaperEditStash({Future<Directory> Function()? rootResolver})
      : _rootResolver = rootResolver ?? _defaultRoot;

  final Future<Directory> Function() _rootResolver;

  static const stashDirName = 'paper_edit_stash';
  static const maxSourceBytes = 80 * 1024 * 1024;
  static const maxTotalBytes = 512 * 1024 * 1024;

  Future<Directory> stashRoot() async {
    final docs = await _rootResolver();
    final dir = Directory(p.join(docs.path, stashDirName));
    if (!await dir.exists()) {
      await dir.create(recursive: true);
    }
    return dir;
  }

  Future<Directory> paperDir(String cacheId) async {
    final id = cacheId.trim();
    return Directory(p.join((await stashRoot()).path, id));
  }

  Future<File> _sourceFile(String cacheId, String filename) async {
    return File(p.join((await paperDir(cacheId)).path, filename));
  }

  Future<File> metaFile(String cacheId) async {
    return File(p.join((await paperDir(cacheId)).path, 'meta.json'));
  }

  Future<Directory> pagePreviewDir(String cacheId) async {
    final dir = Directory(
      p.join((await paperDir(cacheId)).path, 'page_previews'),
    );
    if (!await dir.exists()) {
      await dir.create(recursive: true);
    }
    return dir;
  }

  Future<File> pagePreviewFile(String cacheId, int pageIndex) async {
    return File(
      p.join((await pagePreviewDir(cacheId)).path, 'p$pageIndex.png'),
    );
  }

  Future<PaperStashMeta?> readMeta(String cacheId) async {
    final f = await metaFile(cacheId);
    if (!await f.exists()) return null;
    try {
      final raw = jsonDecode(await f.readAsString()) as Map<String, dynamic>;
      return PaperStashMeta.fromJson(raw);
    } catch (_) {
      return null;
    }
  }

  Future<bool> hasSource(String cacheId) async {
    final meta = await readMeta(cacheId);
    if (meta == null || !meta.isValid) return false;
    final f = await _sourceFile(cacheId, meta.sourceFilename);
    if (!await f.exists()) return false;
    final len = await f.length();
    return len > 0 && len <= maxSourceBytes;
  }

  Future<Uint8List?> readSourceBytes(String cacheId) async {
    final meta = await readMeta(cacheId);
    if (meta == null) return null;
    final f = await _sourceFile(cacheId, meta.sourceFilename);
    if (!await f.exists()) return null;
    try {
      return await f.readAsBytes();
    } catch (_) {
      return null;
    }
  }

  Future<Uint8List?> readPagePreview(String cacheId, int pageIndex) async {
    final f = await pagePreviewFile(cacheId, pageIndex);
    if (!await f.exists()) return null;
    try {
      return await f.readAsBytes();
    } catch (_) {
      return null;
    }
  }

  Future<PaperStashMeta> saveSource({
    required String cacheId,
    required Uint8List bytes,
    required String filename,
    String contentHash = '',
  }) async {
    if (bytes.isEmpty || bytes.length > maxSourceBytes) {
      throw PaperStashException('source_too_large');
    }
    final id = cacheId.trim();
    final dir = await paperDir(id);
    if (!await dir.exists()) {
      await dir.create(recursive: true);
    }
    final safeName = filename.trim().isEmpty ? 'source.pdf' : filename.trim();
    final dest = await _sourceFile(id, safeName);
    final tmp = File('${dest.path}.tmp');
    await tmp.writeAsBytes(bytes, flush: true);
    if (await dest.exists()) {
      await dest.delete();
    }
    await tmp.rename(dest.path);
    final meta = PaperStashMeta(
      cacheId: id,
      contentHash: contentHash.trim(),
      sourceFilename: safeName,
      sourceBytes: bytes.length,
      savedAt: DateTime.now().toUtc(),
      invalidatedAt: null,
    );
    await (await metaFile(id)).writeAsString(
      '${jsonEncode(meta.toJson())}\n',
      flush: true,
    );
    await _enforceTotalBudget(keepCacheId: id);
    return meta;
  }

  Future<PaperStashMeta?> importFromLocalPath({
    required String cacheId,
    required String localPath,
    String contentHash = '',
  }) async {
    final path = localPath.trim();
    if (path.isEmpty) return null;
    try {
      final f = File(path);
      if (!await f.exists()) return null;
      final bytes = await f.readAsBytes();
      return await saveSource(
        cacheId: cacheId,
        bytes: bytes,
        filename: p.basename(path),
        contentHash: contentHash,
      );
    } catch (_) {
      return null;
    }
  }

  Future<void> writePagePreview(
    String cacheId,
    int pageIndex,
    Uint8List png,
  ) async {
    if (png.isEmpty) return;
    final f = await pagePreviewFile(cacheId, pageIndex);
    await f.writeAsBytes(png, flush: true);
  }

  Future<void> invalidatePreviews(String cacheId) async {
    final previews = Directory(
      p.join((await paperDir(cacheId)).path, 'page_previews'),
    );
    if (await previews.exists()) {
      await previews.delete(recursive: true);
    }
    final meta = await readMeta(cacheId);
    if (meta != null) {
      final next = PaperStashMeta(
        cacheId: meta.cacheId,
        contentHash: meta.contentHash,
        sourceFilename: meta.sourceFilename,
        sourceBytes: meta.sourceBytes,
        savedAt: meta.savedAt,
        invalidatedAt: DateTime.now().toUtc(),
        stashVersion: meta.stashVersion,
      );
      await (await metaFile(cacheId)).writeAsString(
        '${jsonEncode(next.toJson())}\n',
        flush: true,
      );
    }
  }

  Future<void> purge(String cacheId) async {
    final dir = await paperDir(cacheId);
    if (await dir.exists()) {
      await dir.delete(recursive: true);
    }
  }

  Future<void> purgeAll() async {
    final root = await stashRoot();
    if (!await root.exists()) return;
    await for (final e in root.list()) {
      if (e is Directory) {
        await e.delete(recursive: true);
      }
    }
  }

  Future<void> purgeOrphans(Set<String> knownCacheIds) async {
    final known = knownCacheIds.map((e) => e.trim()).where((e) => e.isNotEmpty).toSet();
    final root = await stashRoot();
    if (!await root.exists()) return;
    await for (final e in root.list()) {
      if (e is! Directory) continue;
      if (!known.contains(p.basename(e.path))) {
        await e.delete(recursive: true);
      }
    }
  }

  Future<void> _enforceTotalBudget({String? keepCacheId}) async {
    final root = await stashRoot();
    if (!await root.exists()) return;
    final rows = <({String id, int bytes, DateTime at})>[];
    var total = 0;
    await for (final e in root.list()) {
      if (e is! Directory) continue;
      final id = p.basename(e.path);
      final meta = await readMeta(id);
      final bytes = meta?.sourceBytes ?? 0;
      total += bytes;
      rows.add((id: id, bytes: bytes, at: meta?.savedAt ?? DateTime.utc(1970)));
    }
    if (total <= maxTotalBytes) return;
    rows.sort((a, b) => a.at.compareTo(b.at));
    for (final row in rows) {
      if (total <= maxTotalBytes) break;
      if (keepCacheId != null && row.id == keepCacheId) continue;
      await purge(row.id);
      total -= row.bytes;
    }
  }
}

Future<Directory> _defaultRoot() => getApplicationDocumentsDirectory();
