/// design/309 — advisory titles are extracted on each folder scan and are not stored.
library;

import 'dart:io';

import 'package:path_provider/path_provider.dart';

/// design/309 — advisory titles are not stored. Schema is unused; disk rows are deleted.
const int kPdfAdvisoryCacheSchema = 0;

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

  Future<void> bindUid(String? uid) async {
    _uid = (uid ?? '').trim().isEmpty ? null : uid!.trim();
    await _refusePersist();
  }

  Future<Directory?> _dir() async {
    final u = _uid;
    if (u == null || u.isEmpty) return null;
    final safe = u.replaceAll(RegExp(r'[^a-zA-Z0-9_-]'), '_');
    final base = await getApplicationDocumentsDirectory();
    return Directory('${base.path}/pdf_advisory_cache/u_$safe');
  }

  Future<File?> _file() async {
    final d = await _dir();
    if (d == null) return null;
    return File('${d.path}/index.json');
  }

  /// design/309 — never read a saved title. Delete leftover files instead.
  Future<void> _refusePersist() async {
    try {
      final f = await _file();
      if (f != null && await f.exists()) await f.delete();
      final d = await _dir();
      if (d != null && await d.exists()) {
        await d.delete(recursive: true);
      }
    } catch (_) {}
  }

  Future<PdfAdvisoryCacheEntry?> lookup({
    required String docUri,
    required int sizeBytes,
    required int lastModifiedMs,
  }) async {
    await _refusePersist();
    return null;
  }

  /// design/309 — callers may still pass a title. It is discarded and the disk row is deleted.
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
    if (kPdfAdvisoryCacheSchema != 0 ||
        advisoryTitle.isNotEmpty ||
        docUri.isNotEmpty ||
        sizeBytes < 0 ||
        lastModifiedMs < 0 ||
        advisoryRole.isNotEmpty ||
        advisoryReason.isNotEmpty ||
        extractOk ||
        titleSource.isNotEmpty ||
        advisoryDoi.isNotEmpty ||
        doiSource.isNotEmpty ||
        pairingKey.isNotEmpty ||
        siStatus.isNotEmpty ||
        siStem.isNotEmpty) {
      await _refusePersist();
      return;
    }
    await _refusePersist();
  }

  Future<void> clearBound() async {
    await _refusePersist();
    _uid = null;
  }
}
