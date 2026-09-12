/// design/228 · 229 · 230 · 237 · 239 — disk cache title/role/doi/pairing_key (no path/URI).
library;

import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';

import 'pdf_hash_cache_store.dart';

const int kPdfAdvisoryCacheMaxEntries = 2000;

/// design/229 · 233 · 235 · 236 · 237 · 239 · 254 — bump wipes stale rows (DOCX extract, HTML entities).
const int kPdfAdvisoryCacheSchema = 9;

class PdfAdvisoryCacheEntry {
  const PdfAdvisoryCacheEntry({
    required this.advisoryTitle,
    required this.advisoryRole,
    required this.advisoryReason,
    required this.extractOk,
    this.titleSource = '',
    this.advisoryDoi = '',
    this.doiSource = '',
    this.pairingKey = '',
    this.siStatus = '',
    this.siStem = '',
  });

  final String advisoryTitle;
  final String advisoryRole;
  final String advisoryReason;
  final bool extractOk;

  /// design/230 — `info` | `head_line` | `stem` (empty if older cache row).
  final String titleSource;

  /// design/237 — DOI token only (never logged as evidence plaintext).
  final String advisoryDoi;

  /// `head` | `info` | ''
  final String doiSource;

  /// design/239 — optional precomputed pairing key.
  final String pairingKey;

  /// design/251 — absent | available | unknown | ''
  final String siStatus;

  /// design/251 — ACS SI filename stem hint.
  final String siStem;
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
    final doiSrc = '${row['doi_source'] ?? ''}'.trim().toLowerCase();
    final doiSource = (doiSrc == 'head' || doiSrc == 'info') ? doiSrc : '';
    final si = '${row['si_status'] ?? ''}'.trim().toLowerCase();
    final siStatus = (si == 'absent' || si == 'available' || si == 'unknown')
        ? si
        : '';
    return PdfAdvisoryCacheEntry(
      advisoryTitle: '${row['advisory_title'] ?? ''}'.trim(),
      advisoryRole: role,
      advisoryReason: '${row['advisory_reason'] ?? ''}'.trim(),
      extractOk: row['extract_ok'] == true,
      titleSource: titleSource,
      advisoryDoi: '${row['advisory_doi'] ?? ''}'.trim(),
      doiSource: doiSource,
      pairingKey: '${row['pairing_key'] ?? ''}'.trim(),
      siStatus: siStatus,
      siStem: '${row['si_stem'] ?? ''}'.trim(),
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
    String advisoryDoi = '',
    String doiSource = '',
    String pairingKey = '',
    String siStatus = '',
    String siStem = '',
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
    final dsrc = doiSource.trim().toLowerCase();
    final dsrcOut = (dsrc == 'head' || dsrc == 'info') ? dsrc : '';
    _mem[key] = {
      'advisory_title': advisoryTitle.trim(),
      'advisory_role':
          (role == 'main' || role == 'supplementary') ? role : '',
      'advisory_reason': advisoryReason.trim(),
      'extract_ok': extractOk,
      'title_source': srcOut,
      'advisory_doi': advisoryDoi.trim(),
      'doi_source': dsrcOut,
      'pairing_key': pairingKey.trim(),
      'si_status': () {
        final s = siStatus.trim().toLowerCase();
        return (s == 'absent' || s == 'available' || s == 'unknown') ? s : '';
      }(),
      'si_stem': siStem.trim(),
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
