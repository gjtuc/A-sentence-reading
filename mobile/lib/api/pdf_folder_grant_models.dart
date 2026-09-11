/// design/226 — uid-scoped folder grant prefs (tree URI only).
library;

import 'dart:convert';

const String kPdfFolderGrantPrefsPrefix = 'asr.pdf_folder_grant.v1.u.';
const int kPdfFolderScanMaxItems = 500;

String pdfFolderGrantPrefsKey(String uid) {
  final safe = uid.trim().replaceAll(RegExp(r'[^a-zA-Z0-9_-]'), '_');
  if (safe.isEmpty) return '${kPdfFolderGrantPrefsPrefix}anon';
  return '$kPdfFolderGrantPrefsPrefix$safe';
}

class PdfFolderGrant {
  PdfFolderGrant({
    required this.treeUri,
    required this.displayLabel,
    this.grantedAtMs = 0,
  });

  final String treeUri;
  final String displayLabel;
  final int grantedAtMs;

  Map<String, dynamic> toJson() => {
        'v': 1,
        'tree_uri': treeUri,
        'display_label': displayLabel,
        'granted_at_ms': grantedAtMs,
      };

  static PdfFolderGrant? fromJson(Map<String, dynamic>? m) {
    if (m == null) return null;
    final uri = '${m['tree_uri'] ?? ''}'.trim();
    final label = '${m['display_label'] ?? ''}'.trim();
    if (uri.isEmpty) return null;
    final at = m['granted_at_ms'] is num
        ? (m['granted_at_ms'] as num).toInt()
        : 0;
    return PdfFolderGrant(
      treeUri: uri,
      displayLabel: label.isEmpty ? '폴더' : label,
      grantedAtMs: at < 0 ? 0 : at,
    );
  }

  static PdfFolderGrant? tryParse(String? raw) {
    if (raw == null || raw.trim().isEmpty) return null;
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map) return null;
      return fromJson(Map<String, dynamic>.from(decoded));
    } catch (_) {
      return null;
    }
  }

  String encode() => jsonEncode(toJson());
}

enum PdfHashState { unknown, computing, ready, failed }

enum PdfAdvisoryState { unknown, computing, ready, failed }

class ScannedPdfEntry {
  ScannedPdfEntry({
    required this.docUri,
    required this.displayName,
    required this.sizeBytes,
    required this.lastModifiedMs,
    this.contentHash = '',
    this.hashState = PdfHashState.unknown,
    this.advisoryTitle = '',
    this.advisoryRole = '',
    this.advisoryReason = '',
    this.advisoryState = PdfAdvisoryState.unknown,
  });

  final String docUri;
  final String displayName;
  final int sizeBytes;
  final int lastModifiedMs;
  String contentHash;
  PdfHashState hashState;
  /// design/228 — estimated title (never used as upload wire name).
  String advisoryTitle;
  /// `main` | `supplementary` | ''
  String advisoryRole;
  String advisoryReason;
  PdfAdvisoryState advisoryState;

  ScannedPdfEntry copyWith({
    String? contentHash,
    PdfHashState? hashState,
    String? advisoryTitle,
    String? advisoryRole,
    String? advisoryReason,
    PdfAdvisoryState? advisoryState,
  }) {
    return ScannedPdfEntry(
      docUri: docUri,
      displayName: displayName,
      sizeBytes: sizeBytes,
      lastModifiedMs: lastModifiedMs,
      contentHash: contentHash ?? this.contentHash,
      hashState: hashState ?? this.hashState,
      advisoryTitle: advisoryTitle ?? this.advisoryTitle,
      advisoryRole: advisoryRole ?? this.advisoryRole,
      advisoryReason: advisoryReason ?? this.advisoryReason,
      advisoryState: advisoryState ?? this.advisoryState,
    );
  }
}
