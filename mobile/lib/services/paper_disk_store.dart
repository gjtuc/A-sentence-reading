/// design/185 Phase 1 — on-device paper folder store (session · figures · source).
///
/// Survives process kill. Cloud wipe / handoff ACK are later phases — this store
/// only receives shadow copies after open and merges local-only rows into the list.
library;

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import '../api/paper_models.dart';
import '../api/reading_models.dart';
import 'figure_disk_cache.dart';

const String kPaperDiskStoreDirName = 'asr_papers';
const int kPaperSessionMaxBytes = 8 * 1024 * 1024;
const int kPaperSourceMaxBytes = 80 * 1024 * 1024;

String paperDiskSha256Hex(List<int> bytes) {
  if (bytes.isEmpty) return '';
  return sha256.convert(bytes).toString();
}

/// One row in the local library index (device SoT candidate).
class PaperDiskIndexEntry {
  PaperDiskIndexEntry({
    required this.id,
    required this.title,
    this.source = 'pdf',
    this.updatedAt = '',
    this.sentenceCount = 0,
    this.figureCount = 0,
    this.contentHash = '',
    this.pipelineVersion = '',
    this.hasSource = false,
    this.debone = false,
  });

  factory PaperDiskIndexEntry.fromJson(Map<String, dynamic>? json) {
    if (json == null) {
      return PaperDiskIndexEntry(id: '', title: '');
    }
    int asInt(Object? v) {
      if (v is int) return v;
      if (v is num) return v.toInt();
      return int.tryParse('$v') ?? 0;
    }

    return PaperDiskIndexEntry(
      id: '${json['id'] ?? ''}'.trim(),
      title: '${json['title'] ?? ''}'.trim(),
      source: '${json['source'] ?? 'pdf'}'.trim().isEmpty
          ? 'pdf'
          : '${json['source'] ?? 'pdf'}'.trim(),
      updatedAt: '${json['updated_at'] ?? ''}'.trim(),
      sentenceCount: asInt(json['sentence_count']),
      figureCount: asInt(json['figure_count']),
      contentHash: '${json['content_hash'] ?? ''}'.trim().toLowerCase(),
      pipelineVersion: '${json['pipeline_version'] ?? ''}'.trim(),
      hasSource: json['has_source'] == true,
      debone: json['debone'] == true,
    );
  }

  final String id;
  final String title;
  final String source;
  final String updatedAt;
  final int sentenceCount;
  final int figureCount;
  final String contentHash;
  final String pipelineVersion;
  final bool hasSource;
  final bool debone;

  bool get isValid => id.isNotEmpty && title.isNotEmpty;

  Map<String, dynamic> toJson() => {
        'id': id,
        'title': title,
        'source': source,
        'updated_at': updatedAt,
        'sentence_count': sentenceCount,
        'figure_count': figureCount,
        'content_hash': contentHash,
        'pipeline_version': pipelineVersion,
        'has_source': hasSource,
        'debone': debone,
      };

  PaperEntry toPaperEntry() => PaperEntry(
        id: id,
        title: title,
        source: source,
        updatedAt: updatedAt,
        sentenceCount: sentenceCount,
        figureCount: figureCount,
        debone: debone,
        pipelineVersion: pipelineVersion,
        hasSource: hasSource,
        ingestStatus: 'local',
        libraryTag: '로컬',
      );
}

/// Handoff-style manifest (sha256 per relative path).
class PaperDiskManifest {
  PaperDiskManifest({
    required this.cacheId,
    required this.uid,
    this.contentHash = '',
    this.artifactGen = '',
    this.updatedAt = '',
    Map<String, PaperDiskFileMeta>? files,
    this.version = 1,
  }) : files = files ?? {};

  final int version;
  final String cacheId;
  final String uid;
  String contentHash;
  String artifactGen;
  String updatedAt;
  final Map<String, PaperDiskFileMeta> files;

  Map<String, dynamic> toJson() => {
        'version': version,
        'cache_id': cacheId,
        'uid': uid,
        'content_hash': contentHash,
        'artifact_gen': artifactGen,
        'updated_at': updatedAt,
        'files': {
          for (final e in files.entries) e.key: e.value.toJson(),
        },
      };

  static PaperDiskManifest? fromJson(Map<String, dynamic>? json) {
    if (json == null) return null;
    final cid = '${json['cache_id'] ?? ''}'.trim();
    if (cid.isEmpty) return null;
    final files = <String, PaperDiskFileMeta>{};
    final raw = json['files'];
    if (raw is Map) {
      for (final e in raw.entries) {
        final rel = '${e.key}'.trim();
        if (rel.isEmpty || e.value is! Map) continue;
        final meta = PaperDiskFileMeta.fromJson(
          Map<String, dynamic>.from(e.value as Map),
        );
        if (meta != null) files[rel] = meta;
      }
    }
    return PaperDiskManifest(
      version: (json['version'] as num?)?.toInt() ?? 1,
      cacheId: cid,
      uid: '${json['uid'] ?? ''}'.trim(),
      contentHash: '${json['content_hash'] ?? ''}'.trim(),
      artifactGen: '${json['artifact_gen'] ?? ''}'.trim(),
      updatedAt: '${json['updated_at'] ?? ''}'.trim(),
      files: files,
    );
  }
}

class PaperDiskFileMeta {
  const PaperDiskFileMeta({
    required this.size,
    required this.sha256,
  });

  final int size;
  final String sha256;

  Map<String, dynamic> toJson() => {
        'size': size,
        'sha256': sha256,
      };

  static PaperDiskFileMeta? fromJson(Map<String, dynamic>? json) {
    if (json == null) return null;
    final sha = '${json['sha256'] ?? ''}'.trim().toLowerCase();
    if (sha.isEmpty) return null;
    final size = json['size'];
    final n = size is int
        ? size
        : (size is num ? size.toInt() : int.tryParse('$size') ?? 0);
    return PaperDiskFileMeta(size: n, sha256: sha);
  }
}

/// Persistable session map from an opened [ReadingSession] (no large data-URLs).
Map<String, dynamic> readingSessionToPaperDiskJson(ReadingSession s) {
  return {
    'version': 1,
    'session_id': s.sessionId,
    'cache_id': s.cacheId,
    'title': s.title,
    'content_hash': s.contentHash,
    'sentence_index': s.sentenceIndex,
    'figure_index': s.figureIndex,
    'warnings': s.warnings,
    'translate_pending': s.translatePending,
    'supplementary_merged': s.supplementaryMerged,
    if (s.firstFigTableChipSentenceIndex != null)
      'first_fig_table_chip_sentence_index': s.firstFigTableChipSentenceIndex,
    'sentences': [
      for (final row in s.sentences)
        {
          'id': row.id,
          'text': row.text,
          'section': row.section,
          'text_ko': row.textKo,
          if (row.qualityFlags.isNotEmpty) 'quality_flags': row.qualityFlags,
        },
    ],
    'figures': [
      for (final f in s.figures)
        {
          'id': f.id,
          'caption': f.caption,
          'caption_ko': f.captionKo,
          'slot_key': f.slotKey,
          // Prefer on-disk figures/{id}.png — do not embed data-URLs here.
          'image_src': '',
          'file': 'figures/${figureCacheSafeToken(f.id, maxLen: 64)}.png',
        },
    ],
  };
}

class PaperDiskStore {
  PaperDiskStore({
    this.rootResolver,
    this.maxSessionBytes = kPaperSessionMaxBytes,
    this.maxSourceBytes = kPaperSourceMaxBytes,
    this.maxFigureBytes = kFigureDiskMaxBytes,
  });

  /// Test hook — default [getApplicationDocumentsDirectory].
  final Future<Directory> Function()? rootResolver;
  final int maxSessionBytes;
  final int maxSourceBytes;
  final int maxFigureBytes;

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
    return Directory(p.join(docs.path, kPaperDiskStoreDirName, 'u', _uid));
  }

  Future<Directory?> paperDir(String cacheId) async {
    final root = await uidRoot();
    final cid = figureCacheSafeToken(cacheId, maxLen: 32);
    if (root == null || cid.isEmpty) return null;
    return Directory(p.join(root.path, cid));
  }

  Future<File?> _indexFile() async {
    final root = await uidRoot();
    if (root == null) return null;
    return File(p.join(root.path, 'index.json'));
  }

  Future<File?> _sessionFile(String cacheId) async {
    final dir = await paperDir(cacheId);
    if (dir == null) return null;
    return File(p.join(dir.path, 'session.json'));
  }

  Future<File?> _manifestFile(String cacheId) async {
    final dir = await paperDir(cacheId);
    if (dir == null) return null;
    return File(p.join(dir.path, 'manifest.json'));
  }

  Future<Directory?> _figuresDir(String cacheId) async {
    final dir = await paperDir(cacheId);
    if (dir == null) return null;
    return Directory(p.join(dir.path, 'figures'));
  }

  Future<File?> _figureFile(String cacheId, String figureId) async {
    final dir = await _figuresDir(cacheId);
    final fid = figureCacheSafeToken(figureId, maxLen: 64);
    if (dir == null || fid.isEmpty) return null;
    return File(p.join(dir.path, '$fid.png'));
  }

  Future<void> _atomicWriteBytes(File dest, List<int> bytes) async {
    final parent = dest.parent;
    if (!await parent.exists()) {
      await parent.create(recursive: true);
    }
    final tmp = File('${dest.path}.part');
    await tmp.writeAsBytes(bytes, flush: true);
    if (await dest.exists()) {
      await dest.delete();
    }
    await tmp.rename(dest.path);
  }

  Future<void> _atomicWriteString(File dest, String text) async {
    await _atomicWriteBytes(dest, utf8.encode(text));
  }

  Future<List<PaperDiskIndexEntry>> listIndex() async {
    final f = await _indexFile();
    if (f == null || !await f.exists()) return const [];
    try {
      final raw = jsonDecode(await f.readAsString());
      if (raw is! Map) return const [];
      final papers = raw['papers'];
      if (papers is! List) return const [];
      final out = <PaperDiskIndexEntry>[];
      for (final item in papers) {
        if (item is Map) {
          final e = PaperDiskIndexEntry.fromJson(
            Map<String, dynamic>.from(item),
          );
          if (e.isValid) out.add(e);
        }
      }
      return out;
    } catch (_) {
      return const [];
    }
  }

  Future<void> upsertIndex(PaperDiskIndexEntry entry) async {
    if (!isBound || !entry.isValid) return;
    final f = await _indexFile();
    final root = await uidRoot();
    if (f == null || root == null) return;
    if (!await root.exists()) {
      await root.create(recursive: true);
    }
    final cur = await listIndex();
    final next = <PaperDiskIndexEntry>[
      for (final e in cur)
        if (e.id != entry.id) e,
      entry,
    ];
    final payload = {
      'version': 1,
      'uid': _uid,
      'updated_at': DateTime.now().toUtc().toIso8601String(),
      'papers': [for (final e in next) e.toJson()],
    };
    await _atomicWriteString(f, jsonEncode(payload));
  }

  Future<void> removeFromIndex(String cacheId) async {
    final cid = cacheId.trim();
    if (!isBound || cid.isEmpty) return;
    final f = await _indexFile();
    if (f == null || !await f.exists()) return;
    final cur = await listIndex();
    final next = [for (final e in cur) if (e.id != cid) e];
    final payload = {
      'version': 1,
      'uid': _uid,
      'updated_at': DateTime.now().toUtc().toIso8601String(),
      'papers': [for (final e in next) e.toJson()],
    };
    await _atomicWriteString(f, jsonEncode(payload));
  }

  Future<PaperDiskManifest?> loadManifest(String cacheId) async {
    final f = await _manifestFile(cacheId);
    if (f == null || !await f.exists()) return null;
    try {
      final raw = jsonDecode(await f.readAsString());
      if (raw is! Map) return null;
      return PaperDiskManifest.fromJson(Map<String, dynamic>.from(raw));
    } catch (_) {
      return null;
    }
  }

  Future<Map<String, dynamic>?> loadSessionJson(String cacheId) async {
    final f = await _sessionFile(cacheId);
    if (f == null || !await f.exists()) return null;
    try {
      final raw = jsonDecode(await f.readAsString());
      if (raw is! Map) return null;
      return Map<String, dynamic>.from(raw);
    } catch (_) {
      return null;
    }
  }

  Future<bool> hasSession(String cacheId) async {
    final f = await _sessionFile(cacheId);
    return f != null && await f.exists();
  }

  Future<bool> writeSessionJson(
    String cacheId,
    Map<String, dynamic> session, {
    String contentHash = '',
  }) async {
    if (!isBound) return false;
    final f = await _sessionFile(cacheId);
    final dir = await paperDir(cacheId);
    if (f == null || dir == null) return false;
    final encoded = utf8.encode(jsonEncode(session));
    if (encoded.isEmpty || encoded.length > maxSessionBytes) return false;
    try {
      await _atomicWriteBytes(f, encoded);
      await _touchManifestFile(
        cacheId,
        rel: 'session.json',
        bytes: encoded,
        contentHash: contentHash,
      );
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<bool> writeFigureBytes(
    String cacheId, {
    required String figureId,
    required Uint8List bytes,
    String contentHash = '',
  }) async {
    if (!isBound) return false;
    if (bytes.isEmpty || bytes.length > maxFigureBytes) return false;
    final f = await _figureFile(cacheId, figureId);
    final fid = figureCacheSafeToken(figureId, maxLen: 64);
    if (f == null || fid.isEmpty) return false;
    try {
      await _atomicWriteBytes(f, bytes);
      await _touchManifestFile(
        cacheId,
        rel: 'figures/$fid.png',
        bytes: bytes,
        contentHash: contentHash,
      );
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<Uint8List?> readFigureBytes(String cacheId, String figureId) async {
    final f = await _figureFile(cacheId, figureId);
    if (f == null || !await f.exists()) return null;
    try {
      final bytes = await f.readAsBytes();
      if (bytes.isEmpty || bytes.length > maxFigureBytes) return null;
      return Uint8List.fromList(bytes);
    } catch (_) {
      return null;
    }
  }

  Future<bool> writeSourceBytes(
    String cacheId, {
    required Uint8List bytes,
    String suffix = '.pdf',
    String contentHash = '',
  }) async {
    if (!isBound) return false;
    if (bytes.isEmpty || bytes.length > maxSourceBytes) return false;
    final ext = suffix.startsWith('.') ? suffix.toLowerCase() : '.$suffix';
    if (ext != '.pdf' && ext != '.docx') return false;
    final dir = await paperDir(cacheId);
    if (dir == null) return false;
    final f = File(p.join(dir.path, 'source$ext'));
    try {
      await _atomicWriteBytes(f, bytes);
      await _touchManifestFile(
        cacheId,
        rel: 'source$ext',
        bytes: bytes,
        contentHash: contentHash,
      );
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<void> _touchManifestFile(
    String cacheId, {
    required String rel,
    required List<int> bytes,
    String contentHash = '',
  }) async {
    final cid = figureCacheSafeToken(cacheId, maxLen: 32);
    if (cid.isEmpty) return;
    var m = await loadManifest(cacheId);
    m ??= PaperDiskManifest(cacheId: cid, uid: _uid);
    final ch = contentHash.trim().toLowerCase();
    if (ch.isNotEmpty) m.contentHash = ch;
    m.files[rel] = PaperDiskFileMeta(
      size: bytes.length,
      sha256: paperDiskSha256Hex(bytes),
    );
    m.updatedAt = DateTime.now().toUtc().toIso8601String();
    final f = await _manifestFile(cacheId);
    if (f == null) return;
    await _atomicWriteString(f, jsonEncode(m.toJson()));
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
        final f = await _manifestFile(cacheId);
        if (f != null) {
          await _atomicWriteString(f, jsonEncode(m.toJson()));
        }
      }
      return false;
    }
    await purge(cacheId);
    return true;
  }

  Future<void> purge(String cacheId) async {
    final dir = await paperDir(cacheId);
    if (dir != null && await dir.exists()) {
      try {
        await dir.delete(recursive: true);
      } catch (_) {}
    }
    await removeFromIndex(cacheId);
  }

  /// After a successful cloud open — shadow-copy session + decoded figure PNGs.
  Future<bool> shadowPersistReadingSession(ReadingSession session) async {
    if (!isBound || !session.isValid || session.cacheId.isEmpty) return false;
    final cid = session.cacheId.trim();
    final ch = session.contentHash;
    if (ch.isNotEmpty) {
      await ensureContentHash(cid, ch);
    }
    final sessionMap = readingSessionToPaperDiskJson(session);
    final okSession = await writeSessionJson(cid, sessionMap, contentHash: ch);
    if (!okSession) return false;

    var figOk = 0;
    for (final f in session.figures) {
      final decoded = decodeRasterDataUrl(f.imageSrc);
      if (decoded == null || decoded.bytes.isEmpty) continue;
      final w = await writeFigureBytes(
        cid,
        figureId: f.id,
        bytes: decoded.bytes,
        contentHash: ch,
      );
      if (w) figOk += 1;
    }

    await upsertIndex(
      PaperDiskIndexEntry(
        id: cid,
        title: session.title.trim().isEmpty ? cid : session.title.trim(),
        updatedAt: DateTime.now().toUtc().toIso8601String(),
        sentenceCount: session.sentenceCount,
        figureCount: session.figureCount,
        contentHash: ch,
        hasSource: false,
        debone: false,
      ),
    );
    return figOk >= 0;
  }

  /// Merge remote library rows with local-only disk papers (Phase 1).
  Future<List<PaperEntry>> mergeRemoteWithLocal(List<PaperEntry> remote) async {
    final local = await listIndex();
    if (local.isEmpty) return remote;
    final remoteIds = {for (final e in remote) e.id};
    final extra = <PaperEntry>[
      for (final e in local)
        if (e.isValid && !remoteIds.contains(e.id) && await hasSession(e.id))
          e.toPaperEntry(),
    ];
    if (extra.isEmpty) return remote;
    return [...remote, ...extra];
  }
}
