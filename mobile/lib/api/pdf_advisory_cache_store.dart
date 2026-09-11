/// design/228 · 229 · 230 — disk cache for advisory title/role (no path/URI values).
library;

import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';

import 'pdf_hash_cache_store.dart';

const int kPdfAdvisoryCacheMaxEntries = 2000;

/// design/229 · 233 — bump wipes stale SI / journal-as-title advisories.
const int kPdfAdvisoryCacheSchema = 3;

class PdfAdvisoryCacheEntry {
  const PdfAdvisoryCacheEntry({
    required this.advisoryTitle,
    required this.advisoryRole,
    required this.advisoryReason,
    required this.extractOk,
    this.titleSource = '',
  });

  final String advisoryTitle;
  final String advisoryRole;
  final String advisoryReason;
  final bool extractOk;

  /// design/230 — `info` | `head_line` | `stem` (empty if older cache row).
  final String titleSource;
}

class PdfAdvisoryCacheStore {
  PdfAdvisoryCacheStore();

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
    final d = Directory('${base.path}/pdf_advisory_cache/u_$safe');
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
      final schema = decoded['v'];
      if (schema is! num || schema.toInt() != kPdfAdvisoryCacheSchema) {
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
        final v = e.value;
        if (v is! Map) continue;
        out['${e.key}'] = Map<String, dynamic>.from(v);
      }
      _mem = out;
    } catch (_) {
      _mem = {};
    }
  }

  Future<void> _persist() async {
    final f = await _file();
    if (f == null) return;
    if (_mem.length > kPdfAdvisoryCacheMaxEntries) {
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
      final drop = ranked.length - kPdfAdvisoryCacheMaxEntries;
      for (var i = 0; i < drop; i++) {
        _mem.remove(ranked[i].key);
      }
    }
    await f.writeAsString(
      jsonEncode({'v': kPdfAdvisoryCacheSchema, 'entries': _mem}),
      flush: true,
    );
  }

  Future<PdfAdvisoryCacheEntry?> lookup({
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
    final role = '${row['advisory_role'] ?? ''}'.trim().toLowerCase();
    if (role.isNotEmpty && role != 'main' && role != 'supplementary') {
      return null;
    }
    final src = '${row['title_source'] ?? ''}'.trim().toLowerCase();
    final titleSource = (src == 'info' || src == 'head_line' || src == 'stem')
        ? src
        : '';
    return PdfAdvisoryCacheEntry(
      advisoryTitle: '${row['advisory_title'] ?? ''}'.trim(),
      advisoryRole: role,
      advisoryReason: '${row['advisory_reason'] ?? ''}'.trim(),
      extractOk: row['extract_ok'] == true,
      titleSource: titleSource,
    );
  }

  Future<void> put({
    required String docUri,
    required int sizeBytes,
    required int lastModifiedMs,
    required String advisoryTitle,
    required String advisoryRole,
    required String advisoryReason,
    required bool extractOk,
    String titleSource = '',
  }) async {
    await _ensureLoaded();
    final key = pdfHashCacheKey(
      docUri: docUri,
      sizeBytes: sizeBytes,
      lastModifiedMs: lastModifiedMs,
    );
    final role = advisoryRole.trim().toLowerCase();
    final src = titleSource.trim().toLowerCase();
    final srcOut =
        (src == 'info' || src == 'head_line' || src == 'stem') ? src : '';
    _mem[key] = {
      'advisory_title': advisoryTitle.trim(),
      'advisory_role':
          (role == 'main' || role == 'supplementary') ? role : '',
      'advisory_reason': advisoryReason.trim(),
      'extract_ok': extractOk,
      'title_source': srcOut,
      'size_bytes': sizeBytes,
      'last_modified_ms': lastModifiedMs,
      'computed_at_ms': DateTime.now().millisecondsSinceEpoch,
    };
    await _persist();
  }

  Future<void> clearBound() async {
    try {
      final f = await _file();
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
