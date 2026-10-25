/// design/226 — uid-scoped folder grant prefs (tree URI only).
/// design/237 — advisoryDoi · design/239 — set pairing list items · pairingKey (0.3.235).
library;

import 'dart:convert';

import '../pdf/advisory_title.dart';
import '../pdf/normalize_pairing_key.dart';
import '../pdf/paper_title_key.dart';

const String kPdfFolderGrantPrefsPrefix = 'asr.pdf_folder_grant.v1.u.';
/// design/248 — separate Downloads tree grant (user-picked; not auto).
const String kPdfDownloadsGrantPrefsPrefix = 'asr.pdf_downloads_grant.v1.u.';
const int kPdfFolderScanMaxItems = 500;

String pdfFolderGrantPrefsKey(String uid) {
  final safe = uid.trim().replaceAll(RegExp(r'[^a-zA-Z0-9_-]'), '_');
  if (safe.isEmpty) return '${kPdfFolderGrantPrefsPrefix}anon';
  return '$kPdfFolderGrantPrefsPrefix$safe';
}

String pdfDownloadsGrantPrefsKey(String uid) {
  final safe = uid.trim().replaceAll(RegExp(r'[^a-zA-Z0-9_-]'), '_');
  if (safe.isEmpty) return '${kPdfDownloadsGrantPrefsPrefix}anon';
  return '$kPdfDownloadsGrantPrefsPrefix$safe';
}

/// design/248 — PDF import list browse target.
enum PdfImportBrowseMode { papers, downloads }

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
    this.siStatus = '',
    this.siStem = '',
    this.boxTitle = '',
    this.verifiedTitle = '',
    this.titleShown = 'box',
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

  /// design/251 — absent | available | unknown | ''
  String siStatus;

  /// design/251 — ACS SI stem hint from head.
  String siStem;

  /// Wide-box title. Filled on folder open.
  String boxTitle;

  /// 1000-char verify. Empty until the user flips the switch.
  String verifiedTitle;

  /// `box` or `verified`. Last displayed side.
  String titleShown;

  bool titleSwitchBusy = false;

  /// Resolved pairing key for set/mate logic.
  String get effectivePairingKey {
    final k = pairingKey.trim();
    if (k.isNotEmpty) {
      return isUsablePairingKey(k) ? k : '';
    }
    final fromTitle = normalizePairingKey(advisoryTitle);
    return isUsablePairingKey(fromTitle) ? fromTitle : '';
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
    String? siStatus,
    String? siStem,
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
      siStatus: siStatus ?? this.siStatus,
      siStem: siStem ?? this.siStem,
      boxTitle: this.boxTitle,
      verifiedTitle: this.verifiedTitle,
      titleShown: this.titleShown,
    );
  }
}

/// design/401 — a rescan of an unchanged file keeps the entry this run already
/// read, including one still being read. The find watch rescans every 4 s for two
/// minutes, and each rescan used to reset every title and cancel the read in
/// flight, so a folder longer than one batch never finished. Nothing is written to
/// disk: a fresh app start still reads every file (design/309).
ScannedPdfEntry? keptScanEntry(
  ScannedPdfEntry? prev, {
  required String displayName,
  required int sizeBytes,
  required int lastModifiedMs,
}) {
  if (prev == null || prev.advisoryState == PdfAdvisoryState.unknown) return null;
  if (prev.displayName != displayName ||
      prev.sizeBytes != sizeBytes ||
      prev.lastModifiedMs != lastModifiedMs) {
    return null;
  }
  return prev;
}

/// design/401 — a cancelled read leaves nothing marked as in progress, or a kept
/// entry would show 제목 확인 중 forever.
void releaseAbandonedReads(Iterable<ScannedPdfEntry> pending) {
  for (final e in pending) {
    if (e.advisoryState == PdfAdvisoryState.computing) {
      e.advisoryState = PdfAdvisoryState.unknown;
    }
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

/// design/457 — the title key a file is known by: a recognized main-paper title.
/// An SI file goes by its hash only; its title is the main paper's.
String importEntryTitleKey(ScannedPdfEntry e) {
  if (e.advisoryState != PdfAdvisoryState.ready) return '';
  if (e.advisoryRole.trim().toLowerCase() == 'supplementary') return '';
  if (!_displayedTitleCanPair(e)) return '';
  return paperTitleKey(e.advisoryTitle);
}

/// design/457 — papers known by PDF hash or title key (kept / read on any device).
class PaperMarks {
  const PaperMarks({this.hashes = const {}, this.titles = const {}});

  final Set<String> hashes;
  final Set<String> titles;

  bool get isEmpty => hashes.isEmpty && titles.isEmpty;

  bool hasHash(ScannedPdfEntry e) {
    final h = e.contentHash.trim().toLowerCase();
    return h.length == 64 && hashes.contains(h);
  }

  bool hasTitle(ScannedPdfEntry e) {
    if (titles.isEmpty) return false;
    final t = importEntryTitleKey(e);
    return t.isNotEmpty && titles.contains(t);
  }

  bool has(ScannedPdfEntry e) => hasHash(e) || hasTitle(e);

  /// A set row: both files by hash, or the paper by its main file's title.
  bool hasSet(PdfImportSetItem s) => (hasHash(s.main) && hasHash(s.si)) || hasTitle(s.main);
}

/// design/445 — the rows whose paper is not marked read. A set goes by its main
/// file, as its 다 읽음 badge does, so a done set leaves no stray SI row.
List<PdfImportListItem> withoutReadDone(
  List<PdfImportListItem> items,
  Set<String> doneHashes,
) =>
    withoutMarked(items, PaperMarks(hashes: doneHashes));

/// design/457 — [withoutReadDone] by hash or title key.
List<PdfImportListItem> withoutMarked(
  List<PdfImportListItem> items,
  PaperMarks marks,
) {
  if (marks.isEmpty) return items;
  bool done(ScannedPdfEntry e) => marks.has(e);
  return [
    for (final item in items)
      if (!switch (item) {
        PdfImportSingleItem(:final entry) => done(entry),
        PdfImportSetItem(:final main) => done(main),
      })
        item,
  ];
}

final RegExp _searchDashes = RegExp('[\u2010-\u2015\u2212]');
final RegExp _searchSpaces = RegExp(r'\s+');

String _searchFold(String s) =>
    s.toLowerCase().replaceAll(_searchDashes, '-');

/// design/446 — rows whose file names or recognized titles hold every word of
/// [query], in any order. A set row is searched by both of its files.
List<PdfImportListItem> matchingSearch(
  List<PdfImportListItem> items,
  String query,
) {
  final words = _searchFold(query)
      .split(_searchSpaces)
      .where((w) => w.isNotEmpty)
      .toList();
  if (words.isEmpty) return items;
  String text(ScannedPdfEntry e) => '${e.displayName}\n${e.advisoryTitle}';
  return [
    for (final item in items)
      if (() {
        final hay = _searchFold(switch (item) {
          PdfImportSingleItem(:final entry) => text(entry),
          PdfImportSetItem(:final main, :final si) => '${text(main)}\n${text(si)}',
        });
        return words.every(hay.contains);
      }())
        item,
  ];
}

bool _advisoryTitleNeedsMateBorrow(String title) {
  final t = title.trim();
  if (t.isEmpty) return true;
  return isLowQualityStemTitle(t);
}

bool _displayedTitleCanPair(ScannedPdfEntry e) {
  final shown = e.advisoryTitle.trim();
  if (shown.isEmpty) return false;
  if (isAdvisoryTitleChrome(shown)) return false;
  if (isLowQualityStemTitle(shown)) return false;
  if (looksLikeAuthorLine(shown)) return false;
  final stem = stemFromDisplayName(e.displayName);
  if (stem.isNotEmpty &&
      normalizePairingKey(shown) == normalizePairingKey(stem)) {
    return false;
  }
  return isUsablePairingKey(normalizePairingKey(shown));
}

/// design/276 — SI with empty/weak title borrows ready main mate title (display only).
int applyAdvisoryMateTitleBorrow(List<ScannedPdfEntry> entries) {
  final byKey = <String, List<ScannedPdfEntry>>{};
  for (final e in entries) {
    if (e.advisoryState != PdfAdvisoryState.ready) continue;
    final key = e.effectivePairingKey;
    if (key.isEmpty) continue;
    byKey.putIfAbsent(key, () => []).add(e);
  }
  var n = 0;
  for (final group in byKey.values) {
    ScannedPdfEntry? main;
    for (final e in group) {
      if (e.advisoryRole.trim().toLowerCase() != 'main') continue;
      if (e.advisoryTitle.trim().isEmpty) continue;
      if (isLowQualityStemTitle(e.advisoryTitle)) continue;
      if (looksLikeAuthorLine(e.advisoryTitle)) continue;
      if (isAdvisoryTitleChrome(e.advisoryTitle)) continue;
      main = e;
      break;
    }
    if (main == null) continue;
    for (final e in group) {
      if (e.docUri == main.docUri) continue;
      if (e.advisoryRole.trim().toLowerCase() != 'supplementary') continue;
      if (!_advisoryTitleNeedsMateBorrow(e.advisoryTitle)) continue;
      e.advisoryTitle = main.advisoryTitle;
      n += 1;
    }
  }
  return n;
}

/// Group ready advisories: exactly one main + one SI sharing pairing key → set.
({List<PdfImportListItem> items, int nSets, int nSingles, int nGap})
    buildPdfImportListItems(List<ScannedPdfEntry> entries) {
  // design/276 — fill SI display titles before grouping.
  applyAdvisoryMateTitleBorrow(entries);

  final ready = <ScannedPdfEntry>[];
  final pending = <ScannedPdfEntry>[];
  for (final e in entries) {
    // design/276 — usable soft-pair key may join sets even when title still empty.
    if (e.advisoryState == PdfAdvisoryState.ready &&
        (e.advisoryTitle.trim().isNotEmpty ||
            e.effectivePairingKey.isNotEmpty)) {
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
      if (_advisoryTitleNeedsMateBorrow(si.advisoryTitle) &&
          main.advisoryTitle.trim().isNotEmpty) {
        si.advisoryTitle = main.advisoryTitle;
      }
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

  final openMains = <ScannedPdfEntry>[];
  final openSis = <ScannedPdfEntry>[];
  for (final e in ready) {
    if (used.contains(e.docUri)) continue;
    if (!_displayedTitleCanPair(e)) continue;
    final role = e.advisoryRole.trim().toLowerCase();
    if (role == 'supplementary') {
      openSis.add(e);
    } else if (role == 'main') {
      openMains.add(e);
    }
  }
  final siByMain = <String, List<ScannedPdfEntry>>{};
  final mainBySi = <String, List<ScannedPdfEntry>>{};
  for (final main in openMains) {
    final mk = normalizePairingKey(main.advisoryTitle);
    for (final si in openSis) {
      if (!pairingKeysWithinTypos(mk, normalizePairingKey(si.advisoryTitle))) {
        continue;
      }
      siByMain.putIfAbsent(main.docUri, () => []).add(si);
      mainBySi.putIfAbsent(si.docUri, () => []).add(main);
    }
  }
  for (final main in openMains) {
    final mates = siByMain[main.docUri] ?? const <ScannedPdfEntry>[];
    if (mates.length != 1) continue;
    final si = mates.single;
    final back = mainBySi[si.docUri] ?? const <ScannedPdfEntry>[];
    if (back.length != 1 || back.single.docUri != main.docUri) continue;
    items.add(
      PdfImportSetItem(
        main: main,
        si: si,
        pairingKey: normalizePairingKey(main.advisoryTitle),
      ),
    );
    used.add(main.docUri);
    used.add(si.docUri);
    nSets += 1;
  }

  // design/456 — the titles differ (an SI cover read badly) but both files print
  // the same DOI: one main + one SI with that DOI are a set.
  final byDoi = <String, List<ScannedPdfEntry>>{};
  for (final e in ready) {
    if (used.contains(e.docUri)) continue;
    final k = doiPairingKey(e.advisoryDoi);
    if (k != null) byDoi.putIfAbsent(k, () => []).add(e);
  }
  for (final entry in byDoi.entries) {
    final mains = [
      for (final e in entry.value)
        if (e.advisoryRole.trim().toLowerCase() == 'main') e,
    ];
    final sis = [
      for (final e in entry.value)
        if (e.advisoryRole.trim().toLowerCase() == 'supplementary') e,
    ];
    if (mains.length != 1 || sis.length != 1) continue;
    final main = mains.single;
    final si = sis.single;
    if (main.advisoryTitle.trim().isNotEmpty) si.advisoryTitle = main.advisoryTitle;
    items.add(PdfImportSetItem(main: main, si: si, pairingKey: entry.key));
    used.add(main.docUri);
    used.add(si.docUri);
    nSets += 1;
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
  final doi = doiPairingKey(e.advisoryDoi);
  if (key.isEmpty && doi == null) return false;
  final role = e.advisoryRole.trim().toLowerCase();
  final want = role == 'supplementary' ? 'main' : 'supplementary';
  if (role != 'main' && role != 'supplementary') return false;
  for (final o in all) {
    if (o.docUri == e.docUri) continue;
    if (o.advisoryState != PdfAdvisoryState.ready) continue;
    if (o.advisoryRole.trim().toLowerCase() != want) continue;
    if (key.isNotEmpty && o.effectivePairingKey == key) return true;
    if (doi != null && doiPairingKey(o.advisoryDoi) == doi) return true;
  }
  return false;
}
