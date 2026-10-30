/// design/492 — documents attached behind a paper (Dart twin of
/// `sentence_reading/cache/doc_parts.py`).
library;

import 'paper_models.dart';

const List<String> kPartSections = ['supplementary', 'review', 'attached'];

const Map<String, String> _figPrefix = {
  'supplementary': 'si-',
  'review': 'rv-',
  'attached': 'at-',
};
const Map<String, String> _sentPrefix = {
  'supplementary': 'si_',
  'review': 'rv_',
  'attached': 'at_',
};
const Map<String, String> _sectionTags = {
  'supplementary': '보충',
  'review': '심사',
  'attached': '첨부',
};

/// What a part is called in the merge dialog and the tooltip.
const Map<String, String> kPartSectionNames = {
  'supplementary': '보충 자료',
  'review': '심사 기록',
  'attached': '붙인 문서',
};

final RegExp _nature = RegExp(r'(?<!\d)s?(\d{5})[-_](\d{3,4})[-_](\d{5})(?!\d)');
final RegExp _partMark = RegExp(
  r'[-_ .](?:si|sup|supp|suppl|supporting|supplement|supplementary|esm|moesm\d*'
  r'|mmc\d*|main|appendix|peer[-_ ]?review|review|reviews|reviewer)(?![a-z])',
);
final RegExp _ext = RegExp(r'\.(?:pdf|docx?)$');

String cleanSourceName(Object? raw) {
  final s = '${raw ?? ''}'.replaceAll('\\', '/').split('/').last.trim();
  return s.length > 200 ? s.substring(0, 200) : s;
}

/// Shared key of a paper's files, or '' when the name carries no article id.
String fileArticleKey(Object? name) {
  var stem = cleanSourceName(name).toLowerCase().replaceFirst(_ext, '');
  if (stem.isEmpty) return '';
  final m = _nature.firstMatch(stem);
  if (m != null) {
    final year = (int.parse(m.group(2)!) % 100).toString().padLeft(2, '0');
    return 'n:${m.group(1)}-$year-${m.group(3)}';
  }
  final cut = _partMark.firstMatch(stem);
  if (cut != null) stem = stem.substring(0, cut.start);
  stem = stem.replaceAll(RegExp(r'^[ \-_.]+|[ \-_.]+$'), '');
  final digits = RegExp(r'\d').allMatches(stem).length;
  if (stem.length < 6 || digits < 4) return '';
  return 's:$stem';
}

String normalizePartSection(Object? raw) {
  final v = '${raw ?? ''}'.trim().toLowerCase();
  return kPartSections.contains(v) ? v : 'attached';
}

String partFigurePrefix(String section) =>
    _figPrefix[normalizePartSection(section)]!;

String partSentencePrefix(String section) =>
    _sentPrefix[normalizePartSection(section)]!;

bool _isSi(PaperEntry e) {
  final r = e.docRole.trim().toLowerCase();
  return r == 'supplementary' || r == 'si' || r == 'supp';
}

/// The reader's kind wins over the analysis, as everywhere since design/490.
String partSectionFor(PaperEntry e) {
  if (_isSi(e)) return 'supplementary';
  return e.effectiveKind == 'review' ? 'review' : 'attached';
}

/// '메인+서플먼터리' for the old one-SI merge, else '메인+보충+심사' and so on.
String mergedTagFor(List<String> sections) {
  if (sections.isEmpty || sections.every((s) => s == 'supplementary')) {
    return '메인+서플먼터리';
  }
  final names = <String>[];
  for (final s in sections) {
    final t = _sectionTags[normalizePartSection(s)];
    if (t != null && !names.contains(t)) names.add(t);
  }
  return '메인+${names.join('+')}';
}

bool _ready(PaperEntry e) {
  final st = e.ingestStatus.trim().toLowerCase();
  return st.isEmpty || st == 'ok' || st == 'local';
}

/// Parts in the order the reader meets them: supplementary, then review, then
/// anything else. Equal sections keep the order they came in.
List<PaperEntry> orderParts(List<PaperEntry> parts) {
  int rank(PaperEntry e) => kPartSections.indexOf(partSectionFor(e));
  final indexed = [for (var i = 0; i < parts.length; i++) (i, parts[i])];
  indexed.sort((a, b) {
    final r = rank(a.$2).compareTo(rank(b.$2));
    return r != 0 ? r : a.$1.compareTo(b.$1);
  });
  return [for (final p in indexed) p.$2];
}

/// After the title pairing: [PaperEntry.mergePartIds] on each paper that has
/// documents to take in. The title-paired SI comes first; then SI and review
/// files that share the paper's file number. A number with two papers on it is
/// ambiguous and links nothing, and an SI paired by title to another paper
/// stays with that paper.
List<PaperEntry> applyFileKeyParts(List<PaperEntry> papers) {
  final byKey = <String, List<int>>{};
  for (var i = 0; i < papers.length; i++) {
    final k = fileArticleKey(papers[i].sourceName);
    if (k.isNotEmpty) byKey.putIfAbsent(k, () => []).add(i);
  }
  final hosts = <int, List<PaperEntry>>{};
  for (final idxs in byKey.values) {
    if (idxs.length < 2) continue;
    final mains = <int>[];
    final parts = <PaperEntry>[];
    for (final i in idxs) {
      final e = papers[i];
      final role = e.docRole.trim().toLowerCase();
      if (role == 'merged' || (!_isSi(e) && e.effectiveKind == 'paper')) {
        mains.add(i);
      } else if (_ready(e) && (_isSi(e) || e.effectiveKind == 'review')) {
        parts.add(e);
      }
    }
    if (mains.length != 1 || parts.isEmpty || !_ready(papers[mains.single])) {
      continue;
    }
    hosts[mains.single] = parts;
  }
  final out = <PaperEntry>[];
  for (var i = 0; i < papers.length; i++) {
    final e = papers[i];
    final ids = <String>[];
    final paired = e.pairedCacheId.trim();
    if (e.canMergeSupplementary && paired.isNotEmpty) ids.add(paired);
    for (final p in orderParts(hosts[i] ?? const [])) {
      final mate = p.pairedCacheId.trim();
      if (ids.contains(p.id) || (mate.isNotEmpty && mate != e.id)) continue;
      ids.add(p.id);
    }
    out.add(
      ids.isEmpty && e.mergePartIds.isEmpty ? e : e.copyWith(mergePartIds: ids),
    );
  }
  return out;
}
