/// design/268–270 — public Documents/문장읽기 mirror orchestration.

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';

import '../platform/documents_mirror_channel.dart';
import 'figure_disk_cache.dart';
import 'paper_disk_store.dart';
import 'shadowing_disk_store.dart';

class DocumentsMirrorStore {
  DocumentsMirrorStore({
    DocumentsMirrorChannel? channel,
    PaperDiskStore? paperDisk,
    ShadowingDiskStore? shadowDisk,
  })  : _channel = channel ?? DocumentsMirrorChannel(),
        _paperDisk = paperDisk,
        _shadowDisk = shadowDisk;

  final DocumentsMirrorChannel _channel;
  PaperDiskStore? _paperDisk;
  ShadowingDiskStore? _shadowDisk;

  String _uid = '';
  String? lastError;
  bool lastRestoreAttempted = false;

  void attachPaperDisk(PaperDiskStore store) => _paperDisk = store;
  void attachShadowDisk(ShadowingDiskStore store) => _shadowDisk = store;

  void bindUid(String? uid) {
    _uid = figureCacheSafeToken(uid ?? '', maxLen: 80);
    lastError = null;
  }

  bool get isBound => _uid.isNotEmpty;

  Future<bool> ensureReady() async {
    if (!isBound) return false;
    if (!await _channel.hasManagePermission()) {
      lastError = '모든 파일 접근 권한이 필요합니다 (설정에서 허용).';
      await _channel.requestManagePermission();
      return false;
    }
    final ok = await _channel.ensureUidRoot(_uid);
    if (!ok) {
      lastError = 'Documents/문장읽기 폴더를 만들지 못했습니다.';
    }
    return ok;
  }

  Future<bool> mirrorPaper(String cacheId) async {
    final paper = _paperDisk;
    final cid = figureCacheSafeToken(cacheId, maxLen: 32);
    if (!isBound || paper == null || cid.isEmpty) return false;
    if (!await ensureReady()) return false;
    try {
      final dir = await paper.paperDir(cid);
      if (dir == null || !await dir.exists()) return false;
      await _mirrorDirectory(dir, 'papers/$cid');
      final shadow = _shadowDisk;
      if (shadow != null) {
        final chunks = await shadow.loadChunkPlanJson(cid);
        if (chunks != null) {
          final bytes = Uint8List.fromList(utf8.encode(jsonEncode(chunks)));
          await _channel.writeBytes(
            uid: _uid,
            relativePath: 'papers/$cid/shadowing/chunks.json',
            bytes: bytes,
          );
        }
      }
      final idx = await paper.listIndex();
      final idxBytes =
          Uint8List.fromList(utf8.encode(jsonEncode(idx.map((e) => e.toJson()).toList())));
      await _channel.writeBytes(
        uid: _uid,
        relativePath: 'index.json',
        bytes: idxBytes,
      );
      lastError = null;
      return true;
    } catch (e) {
      lastError = '미러 저장 실패';
      return false;
    }
  }

  Future<bool> deletePaper(String cacheId) async {
    final cid = figureCacheSafeToken(cacheId, maxLen: 32);
    if (!isBound || cid.isEmpty) return false;
    if (!await _channel.hasManagePermission()) return false;
    return _channel.deletePath(uid: _uid, relativePath: 'papers/$cid');
  }

  /// design/269 — restore only when in-app disk is truly empty.
  Future<int> tryEmptyGateRestore() async {
    lastRestoreAttempted = true;
    final paper = _paperDisk;
    if (!isBound || paper == null) return 0;
    if (!await _channel.hasManagePermission()) return 0;
    if (!await _channel.uidRootExists(_uid)) return 0;
    final localIdx = await paper.listIndex();
    if (localIdx.isNotEmpty) return 0;
    final root = await paper.uidRoot();
    if (root != null && await root.exists()) {
      final kids = root.listSync().whereType<Directory>().toList();
      if (kids.isNotEmpty) return 0;
    }
    final raw = await _channel.readBytes(uid: _uid, relativePath: 'index.json');
    if (raw == null || raw.isEmpty) return 0;
    List<dynamic> entries;
    try {
      final decoded = jsonDecode(utf8.decode(raw));
      if (decoded is! List) return 0;
      entries = decoded;
    } catch (_) {
      lastError = '미러 index가 손상되었습니다.';
      return 0;
    }
    var n = 0;
    for (final e in entries) {
      if (e is! Map) continue;
      final id = '${e['id'] ?? ''}'.trim();
      if (id.isEmpty) continue;
      final ok = await _restorePaper(id);
      if (ok) n += 1;
    }
    if (n == 0 && entries.isNotEmpty) {
      lastError = '미러에서 논문을 복구하지 못했습니다.';
    }
    return n;
  }

  Future<bool> _restorePaper(String cacheId) async {
    final paper = _paperDisk;
    final cid = figureCacheSafeToken(cacheId, maxLen: 32);
    if (paper == null || cid.isEmpty) return false;
    final session = await _channel.readBytes(
      uid: _uid,
      relativePath: 'papers/$cid/session.json',
    );
    if (session == null || session.isEmpty) return false;
    Map<String, dynamic> map;
    try {
      final decoded = jsonDecode(utf8.decode(session));
      if (decoded is! Map) return false;
      map = Map<String, dynamic>.from(decoded);
    } catch (_) {
      return false;
    }
    final ok = await paper.writeSessionJson(cid, map);
    if (!ok) return false;
    final man = await _channel.readBytes(
      uid: _uid,
      relativePath: 'papers/$cid/manifest.json',
    );
    if (man != null && man.isNotEmpty) {
      try {
        final decoded = jsonDecode(utf8.decode(man));
        if (decoded is Map) {
          // Best-effort: rewrite via session path already created paper dir.
          final dir = await paper.paperDir(cid);
          if (dir != null) {
            final f = File(p.join(dir.path, 'manifest.json'));
            await f.writeAsBytes(man, flush: true);
          }
        }
      } catch (_) {}
    }
    final figNames = await _channel.listRelative(
      uid: _uid,
      relativePath: 'papers/$cid/figures',
    );
    for (final name in figNames) {
      if (!name.toLowerCase().endsWith('.png')) continue;
      final bytes = await _channel.readBytes(
        uid: _uid,
        relativePath: 'papers/$cid/figures/$name',
      );
      if (bytes == null) continue;
      final fid = name.replaceAll(RegExp(r'\.png$', caseSensitive: false), '');
      await paper.writeFigureBytes(cid, figureId: fid, bytes: bytes);
    }
    final chunks = await _channel.readBytes(
      uid: _uid,
      relativePath: 'papers/$cid/shadowing/chunks.json',
    );
    final shadow = _shadowDisk;
    if (chunks != null && shadow != null) {
      try {
        final decoded = jsonDecode(utf8.decode(chunks));
        if (decoded is Map) {
          await shadow.writeChunkPlanJson(cid, Map<String, dynamic>.from(decoded));
        }
      } catch (_) {}
    }
    await paper.upsertIndex(
      PaperDiskIndexEntry(
        id: cid,
        title: '${map['title'] ?? ''}',
        sentenceCount: (map['sentences'] is List) ? (map['sentences'] as List).length : 0,
        figureCount: (map['figures'] is List) ? (map['figures'] as List).length : 0,
        contentHash: '${map['content_hash'] ?? ''}'.trim().toLowerCase(),
      ),
      caller: 'mirror',
    );
    return true;
  }

  /// design/270 — flush cursors on library tab return.
  Future<void> flushCursors() async {
    if (!isBound) return;
    if (!await ensureReady()) return;
    try {
      final prefs = await SharedPreferences.getInstance();
      final keys = prefs.getKeys().where((k) {
        return k.startsWith('asr.progress.') ||
            k.startsWith('asr.practice_progress.') ||
            k.startsWith('asr.ai_ask_prompts');
      });
      final bag = <String, dynamic>{};
      for (final k in keys) {
        bag[k] = prefs.get(k);
      }
      final bytes = Uint8List.fromList(utf8.encode(jsonEncode(bag)));
      await _channel.writeBytes(
        uid: _uid,
        relativePath: 'prefs/cursors.json',
        bytes: bytes,
      );
    } catch (_) {
      lastError = '커서 미러 실패';
    }
  }

  Future<void> _mirrorDirectory(Directory src, String relBase) async {
    await for (final entity in src.list(recursive: true, followLinks: false)) {
      if (entity is! File) continue;
      final rel = p.relative(entity.path, from: src.path).replaceAll('\\', '/');
      // Never mirror voice blobs.
      if (rel.contains('/voice/') || rel.startsWith('voice/')) continue;
      final bytes = await entity.readAsBytes();
      await _channel.writeBytes(
        uid: _uid,
        relativePath: '$relBase/$rel',
        bytes: Uint8List.fromList(bytes),
      );
    }
  }
}
