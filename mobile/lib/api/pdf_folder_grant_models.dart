/// design/226 — uid-scoped folder grant prefs (tree URI only).
/// design/237 — advisoryDoi · design/239 — set pairing list items · pairingKey (0.3.235).
library;

import 'dart:convert';

import '../pdf/normalize_pairing_key.dart';

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
    this.advisoryDoi = '',
    this.pairingKey = '',
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

  /// design/237 — DOI from head/info (local only; never in evidence plaintext).
  String advisoryDoi;

  /// design/239 — precomputed pairing key (prefer over re-normalize when set).
  String pairingKey;

  /// Resolved pairing key for set/mate logic.
  String get effectivePairingKey {
    final k = pairingKey.trim();
    if (k.isNotEmpty) return k;
    return normalizePairingKey(advisoryTitle);
  }

  ScannedPdfEntry copyWith({
    String? contentHash,
    PdfHashState? hashState,
    String? advisoryTitle,
    String? advisoryRole,
    String? advisoryReason,
    PdfAdvisoryState? advisoryState,
    String? advisoryDoi,
    String? pairingKey,
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
      advisoryDoi: advisoryDoi ?? this.advisoryDoi,
      pairingKey: pairingKey ?? this.pairingKey,
    );
  }
}

/// design/239 — visible import list: singleton or exact 1 main + 1 SI set.
sealed class PdfImportListItem {
  const PdfImportListItem();
  List<String> get docUris;
}

class PdfImportSingleItem extends PdfImportListItem {
  const PdfImportSingleItem(this.entry);
  final ScannedPdfEntry entry;
  @override
  List<String> get docUris => [entry.docUri];
}

class PdfImportSetItem extends PdfImportListItem {
  const PdfImportSetItem({
    required this.main,
    required this.si,
    required this.pairingKey,
  });
  final ScannedPdfEntry main;
  final ScannedPdfEntry si;
  final String pairingKey;
  @override
  List<String> get docUris => [main.docUri, si.docUri];
}

/// Group ready advisories: exactly one main + one SI sharing pairing key → set.
({List<PdfImportListItem> items, int nSets, int nSingles, int nGap})
    buildPdfImportListItems(List<ScannedPdfEntry> entries) {
  final ready = <ScannedPdfEntry>[];
  final pending = <ScannedPdfEntry>[];
  for (final e in entries) {
    if (e.advisoryState == PdfAdvisoryState.ready &&
        e.advisoryTitle.trim().isNotEmpty) {
      ready.add(e);
    } else {
      pending.add(e);
    }
  }

  final byKey = <String, List<ScannedPdfEntry>>{};
  for (final e in ready) {
    final key = e.effectivePairingKey;
    if (key.isEmpty) {
      pending.add(e);
      continue;
    }
    byKey.putIfAbsent(key, () => []).add(e);
  }

  final items = <PdfImportListItem>[];
  var nSets = 0;
  var nGap = 0;
  final used = <String>{};

  for (final entry in byKey.entries) {
    final group = entry.value;
    ScannedPdfEntry? main;
    ScannedPdfEntry? si;
    var mains = 0;
    var sis = 0;
    for (final e in group) {
      final role = e.advisoryRole.trim().toLowerCase();
      if (role == 'supplementary') {
        sis += 1;
        si ??= e;
      } else if (role == 'main') {
        mains += 1;
        main ??= e;
      }
    }
    if (mains == 1 && sis == 1 && main != null && si != null) {
      items.add(
        PdfImportSetItem(main: main, si: si, pairingKey: entry.key),
      );
      used.add(main.docUri);
      used.add(si.docUri);
      nSets += 1;
    } else if (group.length >= 2 && (mains > 0 || sis > 0)) {
      nGap += 1;
    }
  }

  for (final e in ready) {
    if (used.contains(e.docUri)) continue;
    items.add(PdfImportSingleItem(e));
    used.add(e.docUri);
  }
  for (final e in pending) {
    if (used.contains(e.docUri)) continue;
    items.add(PdfImportSingleItem(e));
  }

  // Stable-ish: sets first then singles by displayName
  items.sort((a, b) {
    final aSet = a is PdfImportSetItem;
    final bSet = b is PdfImportSetItem;
    if (aSet != bSet) return aSet ? -1 : 1;
    String name(PdfImportListItem x) {
      if (x is PdfImportSetItem) return x.main.displayName.toLowerCase();
      if (x is PdfImportSingleItem) return x.entry.displayName.toLowerCase();
      return '';
    }

    return name(a).compareTo(name(b));
  });

  final nSingles = items.whereType<PdfImportSingleItem>().length;
  return (items: items, nSets: nSets, nSingles: nSingles, nGap: nGap);
}

/// design/237 — opposite-role ready mate already in folder (same pairing key).
bool matePresentForEntry(ScannedPdfEntry e, List<ScannedPdfEntry> all) {
  final key = e.effectivePairingKey;
  if (key.isEmpty) return false;
  final role = e.advisoryRole.trim().toLowerCase();
  final want = role == 'supplementary' ? 'main' : 'supplementary';
  if (role != 'main' && role != 'supplementary') return false;
  for (final o in all) {
    if (o.docUri == e.docUri) continue;
    if (o.advisoryState != PdfAdvisoryState.ready) continue;
    if (o.advisoryRole.trim().toLowerCase() != want) continue;
    if (o.effectivePairingKey == key) return true;
  }
  return false;
}
