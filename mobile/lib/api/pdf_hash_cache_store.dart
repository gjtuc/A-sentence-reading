/// design/226 — disk hash cache for folder-list green borders.
library;

import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:path_provider/path_provider.dart';

const int kPdfHashCacheMaxEntries = 2000;

String pdfHashCacheKey({
  required String docUri,
  required int sizeBytes,
  required int lastModifiedMs,
}) {
  final raw = utf8.encode('$docUri|$sizeBytes|$lastModifiedMs');
  return sha256.convert(raw).toString();
}

class PdfHashCacheStore {
  PdfHashCacheStore();

  String? _uid;
  Map<String, Map<String, dynamic>> _mem = {};
  bool _loaded = false;

  Future<void> bindUid(String? uid) async {
    _uid = (uid ?? '').trim().isEmpty ? null : uid!.trim();
    _mem = {};
    _loaded = false;
  }

  Future<Directory?> _dir() async {
    final u = _uid;
    if (u == null || u.isEmpty) return null;
    final safe = u.replaceAll(RegExp(r'[^a-zA-Z0-9_-]'), '_');
    final base = await getApplicationDocumentsDirectory();
    final d = Directory('${base.path}/pdf_hash_cache/u_$safe');
    if (!await d.exists()) {
      await d.create(recursive: true);
    }
    return d;
  }

  Future<File?> _file() async {
    final d = await _dir();
    if (d == null) return null;
    return File('${d.path}/index.json');
  }

  Future<void> _ensureLoaded() async {
    if (_loaded) return;
    _loaded = true;
    final f = await _file();
    if (f == null || !await f.exists()) {
      _mem = {};
      return;
    }
    try {
      final decoded = jsonDecode(await f.readAsString());
      if (decoded is! Map) {
        _mem = {};
        return;
      }
      final entries = decoded['entries'];
      if (entries is! Map) {
        _mem = {};
        return;
      }
      final out = <String, Map<String, dynamic>>{};
      for (final e in entries.entries) {
        final k = '${e.key}';
        final v = e.value;
        if (v is! Map) continue;
        out[k] = Map<String, dynamic>.from(v);
      }
      _mem = out;
    } catch (_) {
      _mem = {};
    }
  }

  Future<void> _persist() async {
    final f = await _file();
    if (f == null) return;
    // LRU trim by computed_at_ms
    if (_mem.length > kPdfHashCacheMaxEntries) {
      final ranked = _mem.entries.toList()
        ..sort((a, b) {
          final am = a.value['computed_at_ms'] is num
              ? (a.value['computed_at_ms'] as num).toInt()
              : 0;
          final bm = b.value['computed_at_ms'] is num
              ? (b.value['computed_at_ms'] as num).toInt()
              : 0;
          return am.compareTo(bm);
        });
      final drop = ranked.length - kPdfHashCacheMaxEntries;
      for (var i = 0; i < drop; i++) {
        _mem.remove(ranked[i].key);
      }
    }
    await f.writeAsString(
      jsonEncode({'v': 1, 'entries': _mem}),
      flush: true,
    );
  }

  Future<String?> lookup({
    required String docUri,
    required int sizeBytes,
    required int lastModifiedMs,
  }) async {
    await _ensureLoaded();
    final key = pdfHashCacheKey(
      docUri: docUri,
      sizeBytes: sizeBytes,
      lastModifiedMs: lastModifiedMs,
    );
    final row = _mem[key];
    if (row == null) return null;
    final h = '${row['content_hash'] ?? ''}'.trim().toLowerCase();
    if (h.length != 64 || !RegExp(r'^[a-f0-9]{64}$').hasMatch(h)) {
      return null;
    }
    return h;
  }

  Future<void> put({
    required String docUri,
    required int sizeBytes,
    required int lastModifiedMs,
    required String contentHash,
  }) async {
    await _ensureLoaded();
    final hash = contentHash.trim().toLowerCase();
    if (hash.length != 64) return;
    final key = pdfHashCacheKey(
      docUri: docUri,
      sizeBytes: sizeBytes,
      lastModifiedMs: lastModifiedMs,
    );
    _mem[key] = {
      'content_hash': hash,
      'size_bytes': sizeBytes,
      'last_modified_ms': lastModifiedMs,
      'computed_at_ms': DateTime.now().millisecondsSinceEpoch,
    };
    await _persist();
  }

  Future<void> clearBound() async {
    final f = await _file();
    try {
      if (f != null && await f.exists()) await f.delete();
      final d = await _dir();
      if (d != null && await d.exists()) {
        await d.delete(recursive: true);
      }
    } catch (_) {}
    _mem = {};
    _loaded = false;
    _uid = null;
  }
}
