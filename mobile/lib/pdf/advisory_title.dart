/// design/228 · 230 · 233 · 236 · 265 · 276 · 277 — weak title heuristic from PDF Info.Title + head text.
library;

import 'doc_role_detect.dart';

final _siLine = RegExp(
  r'^\s*(supplementary\s+(?:information|materials?|data)|supporting\s+information|electronic\s+supplementary)\b',
  caseSensitive: false,
);

/// design/233 — journal chrome / cover lines (not article titles).
final _exactChrome = RegExp(
  r'^(paper|review|article|research|research article|open access|'
  r'supporting information for|contents lists available|'
  r'available online)\b\.?$',
  caseSensitive: false,
);

final _prefixChrome = RegExp(
  r'^(cite this|cite this:|to cite this|doi:|https?://|www\.|'
  // design/236 — RSC / bare journal short-links (e.g. rsc.li/catalysis)
  r'rsc\.li/|[a-z0-9][\w.-]*\.[a-z]{2,}/|'
  r'received |accepted |published |view the article|'
  r'available online|'
  r'this content was downloaded|citation:)',
  caseSensitive: false,
);

// WHY: Dart RegExp rejects inline (?i) ("Invalid group") — use caseSensitive:false.
final _journalChrome = RegExp(
  r'(?:'
  r'^journal of\b'
  r'|^nature catalysis\b'
  r'|^catal\.?\s*sci\.?\s*technol'
  r'|catalysis\s+science\s*(?:&|and)?\s*technology'
  r'|accounts of chemical research'
  r'|chemical engineering journal'
  r'|green chemical engineering'
  r'|scientific reports'
  r'|sustainable energy\s*(?:&|and)?\s*fuels'
  r'|applied physics'
  r'|chem\.?\s*eng\.?\s*j'
  r')',
  caseSensitive: false,
);

final _citeSuffix = RegExp(
  r'\s*(?:to cite this article|cite this article|cite this:|citation:).*$',
  caseSensitive: false,
);

final _acsCodeInfo = RegExp(
  r'^[a-z]{1,4}\d[a-z0-9]*(?:\s+\d+){0,12}$',
  caseSensitive: false,
);

final _danglingEnd = RegExp(
  r'\b(the|a|an|of|and|or|for|to|in|on|with|from|by|as|at)\s*$',
  caseSensitive: false,
);

final _affiliationOrCaption = RegExp(
  r'(?:'
  r'^figure\s*s?\s*\d'
  r'|^fig\.?\s*s?\s*\d'
  r'|^table\s*s?\s*\d'
  r'|^scheme\s*s?\s*\d'
  r'|^department\b'
  r'|^school of\b'
  r'|^university\b'
  r'|^institute\b'
  r'|laboratory\b'
  r'|light source\b'
  r'|@\w+\.\w+'
  r'|orcid'
  r'|^\S+\s+\S+,\s*\S+.*university'
  r')',
  caseSensitive: false,
);

/// design/230 · 265 · 277 — snake enum for evidence (`info` | `head_line` | `stem` | `failed`).
class AdvisoryTitleGuess {
  const AdvisoryTitleGuess({
    required this.title,
    required this.source,
    this.styleSource = '',
    this.styledN = 0,
    this.joinedN = 0,
    this.seedSizePt = 0,
    this.boldSeed = false,
    this.mixedSizeLine = 0,
  });

  final String title;

  /// `info` | `head_line` | `stem` | `failed`
  final String source;

  /// design/277 — `style_join` | `plain_fallback` | `info` | `stem` | `failed` | ''
  final String styleSource;
  final int styledN;
  final int joinedN;
  final double seedSizePt;
  final bool boldSeed;
  final int mixedSizeLine;
}

/// design/277 — one visual head line with font metrics from PdfBox.
class PdfHeadStyledLine {
  const PdfHeadStyledLine({
    required this.text,
    required this.sizePt,
    required this.bold,
    required this.y,
    this.mixedSize = false,
  });

  final String text;
  final double sizePt;
  final bool bold;
  final double y;

  /// True when the line mixed body-size and smaller (sup/sub) glyphs.
  final bool mixedSize;
}

/// design/277 — relative font-size tolerance for title wrap join.
const double kAdvisoryTitleSizeTol = 0.12;

bool isAdvisoryTitleChrome(String raw) {
  final t = raw.trim().replaceAll(RegExp(r'\s+'), ' ');
  if (t.isEmpty) return true;
  if (_exactChrome.hasMatch(t)) return true;
  if (_prefixChrome.hasMatch(t)) return true;
  if (_journalChrome.hasMatch(t)) return true;
  // design/276 — ACS masthead mash ("Research Article pubs.acs.org/acscatalysis").
  if (RegExp(
    r'(?:^|\b)(?:research\s+article|article)\b.*\bpubs\.acs\.org\b',
    caseSensitive: false,
  ).hasMatch(t)) {
    return true;
  }
  if (RegExp(r'\bpubs\.acs\.org/', caseSensitive: false).hasMatch(t) &&
      t.length < 96) {
    return true;
  }
  // design/277 — "Green Chemical Engineering—Article" / "RESEARCH ARTICLE".
  if (RegExp(
    r'(?:\u2014|\u2013|—|–|-)\s*Article\s*$|^research\s+article\s*$',
    caseSensitive: false,
  ).hasMatch(t)) {
    return true;
  }
  // Split masthead fragments: "Science &", "Technology" alone are short;
  // "Catalysis" alone (common RSC masthead) — reject single-token journal-ish.
  if (RegExp(r'^(catalysis|technology|science\s*&?)$', caseSensitive: false)
      .hasMatch(t)) {
    return true;
  }
  // Page crumb like "14, 1712" or "389"
  if (RegExp(r'^[\d,\s\-–—]+$').hasMatch(t)) return true;
  return false;
}

/// Decodes XML / HTML numeric entities (&#x2013;, &#8211;) and named entities.
/// Also strips inline XML/HTML formatting tags (e.g. <i>, <sub>).
String decodeHtmlEntities(String raw, {bool preserveNewlines = false}) {
  var s = raw;
  if (!s.contains('&') && !s.contains('<')) {
    if (preserveNewlines) {
      return s.replaceAll(RegExp(r'[^\S\r\n]+'), ' ').trim();
    }
    return s.trim().replaceAll(RegExp(r'\s+'), ' ');
  }
  // Hex numeric entities: &#x2013; or &#X2013; (optional semicolon)
  s = s.replaceAllMapped(RegExp(r'&#x([0-9a-fA-F]+);?', caseSensitive: false), (m) {
    try {
      final code = int.parse(m.group(1)!, radix: 16);
      return String.fromCharCode(code);
    } catch (_) {
      return m.group(0)!;
    }
  });
  // Decimal numeric entities: &#8211; (optional semicolon)
  s = s.replaceAllMapped(RegExp(r'&#([0-9]+);?'), (m) {
    try {
      final code = int.parse(m.group(1)!);
      return String.fromCharCode(code);
    } catch (_) {
      return m.group(0)!;
    }
  });
  // Common named entities
  s = s
      .replaceAll('&amp;', '&')
      .replaceAll('&lt;', '<')
      .replaceAll('&gt;', '>')
      .replaceAll('&quot;', '"')
      .replaceAll('&apos;', "'")
      .replaceAll('&nbsp;', ' ')
      .replaceAll('&ndash;', '–')
      .replaceAll('&mdash;', '—')
      .replaceAll('&minus;', '−')
      .replaceAll('&times;', '×')
      .replaceAll('&plusmn;', '±');
  // Strip formatting tags like <i>, </i>, <sub>, <sup>
  if (s.contains('<')) {
    s = s.replaceAll(RegExp(r'</?[a-zA-Z0-9]+(?:\s[^>]*)?>'), '');
  }
  if (preserveNewlines) {
    return s.replaceAll(RegExp(r'[^\S\r\n]+'), ' ').trim();
  }
  return s.trim().replaceAll(RegExp(r'\s+'), ' ');
}

String stripCiteSuffix(String raw) {
  final t = decodeHtmlEntities(raw);
  return t.replaceFirst(_citeSuffix, '').trim();
}

/// design/265 · 276 — Info.Title cut mid-phrase (publisher truncation).
bool isTruncatedInfoTitle(String raw) {
  final t = decodeHtmlEntities(raw).trim();
  if (t.length < 20) return false;
  if (t.endsWith('-') || t.endsWith(',') || t.endsWith(':')) return true;
  if (_danglingEnd.hasMatch(t)) return true;
  final parts = t.split(RegExp(r'\s+'));
  if (parts.isEmpty) return false;
  final last = parts.last;
  // design/276 — mid-word cut to a single letter ("… Molecular D").
  if (parts.length >= 4 &&
      last.length == 1 &&
      RegExp(r'^[A-Za-z]$').hasMatch(last)) {
    return true;
  }
  // Two-letter remnant after a long phrase ("… Functio Th").
  if (parts.length >= 5 &&
      last.length == 2 &&
      RegExp(r'^[A-Za-z]{2}$').hasMatch(last)) {
    return true;
  }
  // Ends with a short capitalized token that looks mid-word cut ("Functio").
  // Cap at 8 so complete endings like Diffraction/Spectroscopy stay.
  if (last.length >= 3 &&
      last.length <= 8 &&
      RegExp(r'^[A-Z][a-z]+$').hasMatch(last) &&
      !RegExp(
        r'^(Study|Review|Catalysts?|Methane|Oxide|Carbon|Energy|Water|Hydrogen)$',
        caseSensitive: false,
      ).hasMatch(last)) {
    if (parts.length >= 6) return true;
  }
  return false;
}

/// design/277 — numbered bibliography / reference crumbs from PDF head.
bool looksLikeBibliographyLine(String raw) {
  final t = decodeHtmlEntities(raw).trim();
  if (RegExp(r'^\d{1,3}\.\s+\S').hasMatch(t)) return true;
  if (RegExp(r'\bet\s+al\.\b', caseSensitive: false).hasMatch(t) &&
      RegExp(r'\(\d{4}\)').hasMatch(t) &&
      t.length < 160) {
    return true;
  }
  return false;
}

/// design/265 · 277 — ACS manuscript id dumped into Info.Title.
bool isCodeLikeInfoTitle(String raw) {
  final t = decodeHtmlEntities(raw).trim();
  if (t.isEmpty) return false;
  if (_acsCodeInfo.hasMatch(t)) return true;
  // design/277 — "am2c04149 1..9" / "cs5b00357 1..12"
  if (RegExp(
    r'^[a-z]{1,4}\d[a-z0-9]*\s+\d+\.\.\d+$',
    caseSensitive: false,
  ).hasMatch(t)) {
    return true;
  }
  final digits = t.replaceAll(RegExp(r'\D'), '').length;
  if (t.length <= 24 && digits > t.length * 0.35 && !t.contains(' ')) {
    return true;
  }
  return false;
}

bool looksLikeAffiliationOrCaption(String raw) {
  final t = decodeHtmlEntities(raw).trim();
  if (t.isEmpty) return false;
  if (_affiliationOrCaption.hasMatch(t)) return true;
  if (RegExp(r'^\d+\s*[†‡*]?$').hasMatch(t)) return true;
  return false;
}

/// design/276 — author / contributor masthead lines (not article titles).
bool looksLikeAuthorLine(String raw) {
  final t = decodeHtmlEntities(raw).trim().replaceAll(RegExp(r'\s+'), ' ');
  if (t.length < 16 || t.length > 420) return false;
  // "Name,* Name,* and Name*" or trailing author asterisks.
  final starCommas = RegExp(r'\*').allMatches(t).length;
  final commas = ','.allMatches(t).length;
  if (starCommas >= 1 && commas >= 2) return true;
  if (RegExp(
    r"^[A-Z][-'’.\w]+(?:\s+[A-Z][-'’.\w]+){0,3}"
    r"(?:,\s*[A-Z][-'’.\w]+(?:\s+[A-Z][-'’.\w]+){0,3}\*?)+"
    r"(?:,?\s+and\s+[A-Z])",
  ).hasMatch(t)) {
    return true;
  }
  // Dense "Last, First" style without content words.
  if (commas >= 3 &&
      starCommas >= 1 &&
      !RegExp(
        r'\b(of|for|with|from|over|via|using|toward|towards)\b',
        caseSensitive: false,
      ).hasMatch(t)) {
    return true;
  }
  return false;
}

/// design/265 — filename stem must not become the tile title.
bool isLowQualityStemTitle(String raw) {
  final t = decodeHtmlEntities(raw).trim();
  if (t.isEmpty) return true;
  if (t.length < 8) return true;
  if (RegExp(r'^[\d\W_]+$').hasMatch(t)) return true;
  if (RegExp(r'^\d{1,3}$').hasMatch(t)) return true;
  // ACS / publisher code + optional si suffix
  if (_acsCodeInfo.hasMatch(t)) return true;
  if (RegExp(
    r'^[a-z]{1,4}\d[a-z0-9]*(?:\s+si(?:\s*\d+)*)?$',
    caseSensitive: false,
  ).hasMatch(t)) {
    return true;
  }
  if (RegExp(r'\bsi\s*0*\d+\b', caseSensitive: false).hasMatch(t) &&
      t.length < 28) {
    return true;
  }
  return false;
}

bool looksLikePaperTitle(String raw) {
  final t = stripCiteSuffix(raw);
  if (t.length < 12 || t.length > 350) return false;
  if (_siLine.hasMatch(t)) return false;
  if (isAdvisoryTitleChrome(t)) return false;
  if (isCodeLikeInfoTitle(t)) return false;
  if (looksLikeAffiliationOrCaption(t)) return false;
  if (looksLikeAuthorLine(t)) return false;
  if (looksLikeBibliographyLine(t)) return false;
  if (RegExp(r'^[\d\W_]+$').hasMatch(t)) return false;
  final digits = t.replaceAll(RegExp(r'\D'), '').length;
  if (digits > t.length * 0.5) return false;
  return true;
}

/// design/276 — strip SI / Supporting Information banner; keep remainder.
String stripSiBannerPrefix(String raw) {
  final t = decodeHtmlEntities(raw).trim();
  if (!_siLine.hasMatch(t)) return t;
  return t.replaceFirst(_siLine, '').trim();
}

/// design/265 — shared gate for info / head / stem candidates.
String? qualifyAdvisoryTitleCandidate(
  String raw, {
  bool rejectTruncated = false,
  bool rejectLowQualityStem = false,
}) {
  final t = stripCiteSuffix(raw);
  if (t.isEmpty) return null;
  if (rejectTruncated && isTruncatedInfoTitle(t)) return null;
  if (rejectLowQualityStem && isLowQualityStemTitle(t)) return null;
  if (!looksLikePaperTitle(t)) return null;
  return t;
}

String stemFromDisplayName(String displayName) {
  var n = displayName.trim();
  if (n.toLowerCase().endsWith('.pdf')) {
    n = n.substring(0, n.length - 4);
  } else if (n.toLowerCase().endsWith('.docx')) {
    n = n.substring(0, n.length - 5);
  }
  try {
    n = Uri.decodeComponent(n);
  } catch (_) {}
  n = n.replaceAll(RegExp(r'[_\s-]+$'), '');
  n = n.replaceFirst(RegExp(r'[_\s-]+\d{1,2}$'), '');
  return decodeHtmlEntities(n);
}

String? _prepareTitleLineText(String raw) {
  var t = decodeHtmlEntities(raw);
  if (_siLine.hasMatch(t)) {
    t = stripSiBannerPrefix(t);
    if (t.isEmpty) return null;
  }
  if (isAdvisoryTitleChrome(t)) return null;
  if (looksLikeAffiliationOrCaption(t)) return null;
  if (looksLikeAuthorLine(t)) return null;
  if (looksLikeBibliographyLine(t)) return null;
  if (t.length < 8) return null;
  return t;
}

bool advisoryTitleSizesSimilar(
  double a,
  double b, {
  double tol = kAdvisoryTitleSizeTol,
}) {
  if (a <= 0 || b <= 0) return false;
  final m = a > b ? a : b;
  return ((a - b).abs() / m) <= tol;
}

bool _styleNeighborOk(PdfHeadStyledLine seed, PdfHeadStyledLine other) {
  if (advisoryTitleSizesSimilar(seed.sizePt, other.sizePt)) return true;
  if (seed.bold &&
      other.bold &&
      advisoryTitleSizesSimilar(seed.sizePt, other.sizePt, tol: 0.18)) {
    return true;
  }
  return false;
}

/// design/277 — join adjacent lines with similar font size/weight (not word stubs).
({String title, int seedIndex, int joinedN, double seedSizePt, bool boldSeed, int mixedSizeLine})?
    joinTitleByFontSimilarity(List<PdfHeadStyledLine> lines) {
  if (lines.isEmpty) return null;
  final prepared = <({int i, String text, PdfHeadStyledLine line})>[];
  for (var i = 0; i < lines.length; i++) {
    final t = _prepareTitleLineText(lines[i].text);
    if (t == null) continue;
    prepared.add((i: i, text: t, line: lines[i]));
  }
  if (prepared.isEmpty) return null;

  ({int i, String text, PdfHeadStyledLine line})? seedPrep;
  for (final e in prepared) {
    if (looksLikePaperTitle(e.text) && e.text.length >= 12) {
      seedPrep = e;
      break;
    }
  }
  seedPrep ??= prepared.reduce(
    (a, b) => a.line.sizePt >= b.line.sizePt ? a : b,
  );
  final seedIdxInLines = seedPrep.i;
  final seedLine = seedPrep.line;

  var lo = seedIdxInLines;
  var hi = seedIdxInLines;
  while (lo > 0) {
    final t = _prepareTitleLineText(lines[lo - 1].text);
    if (t == null) break;
    if (!_styleNeighborOk(seedLine, lines[lo - 1])) break;
    lo -= 1;
  }
  while (hi + 1 < lines.length) {
    final t = _prepareTitleLineText(lines[hi + 1].text);
    if (t == null) break;
    if (!_styleNeighborOk(seedLine, lines[hi + 1])) break;
    hi += 1;
  }

  final parts = <String>[];
  var mixed = 0;
  for (var i = lo; i <= hi; i++) {
    final t = _prepareTitleLineText(lines[i].text);
    if (t == null) continue;
    parts.add(t);
    if (lines[i].mixedSize) mixed = 1;
  }
  if (parts.isEmpty) return null;
  final joined = parts.join(' ').replaceAll(RegExp(r'\s+'), ' ').trim();
  if (joined.length < 12) return null;
  return (
    title: joined,
    seedIndex: seedIdxInLines,
    joinedN: parts.length,
    seedSizePt: seedLine.sizePt,
    boldSeed: seedLine.bold,
    mixedSizeLine: mixed,
  );
}

AdvisoryTitleGuess guessAdvisoryTitle({
  required String infoTitle,
  required String headText,
  required String displayName,
  List<PdfHeadStyledLine> styledLines = const [],
}) {
  final qInfo = qualifyAdvisoryTitleCandidate(
    infoTitle,
    rejectTruncated: true,
  );
  if (qInfo != null) {
    return AdvisoryTitleGuess(
      title: qInfo,
      source: 'info',
      styleSource: 'info',
      styledN: styledLines.length,
    );
  }

  if (styledLines.isNotEmpty) {
    final joined = joinTitleByFontSimilarity(styledLines);
    if (joined != null) {
      final q = qualifyAdvisoryTitleCandidate(joined.title);
      final title = q ?? (looksLikePaperTitle(joined.title) ? joined.title : null);
      if (title != null) {
        return AdvisoryTitleGuess(
          title: title,
          source: 'head_line',
          styleSource: 'style_join',
          styledN: styledLines.length,
          joinedN: joined.joinedN,
          seedSizePt: joined.seedSizePt,
          boldSeed: joined.boldSeed,
          mixedSizeLine: joined.mixedSizeLine,
        );
      }
    }
  }

  final rawHead = stripFormatChars(headText).text;
  for (final line in rawHead.split(RegExp(r'[\r\n]+'))) {
    var t = decodeHtmlEntities(line);
    if (t.isEmpty) continue;
    if (_siLine.hasMatch(t)) {
      t = stripSiBannerPrefix(t);
      if (t.isEmpty) continue;
    }
    if (isAdvisoryTitleChrome(t)) continue;
    if (looksLikeAffiliationOrCaption(t)) continue;
    if (looksLikeAuthorLine(t)) continue;
    if (looksLikeBibliographyLine(t)) continue;
    if (t.length < 12) continue;
    final q = qualifyAdvisoryTitleCandidate(t);
    if (q != null) {
      return AdvisoryTitleGuess(
        title: q,
        source: 'head_line',
        styleSource: 'plain_fallback',
        styledN: styledLines.length,
        joinedN: 1,
      );
    }
  }

  final stem = stemFromDisplayName(displayName);
  final qStem = qualifyAdvisoryTitleCandidate(
    stem,
    rejectLowQualityStem: true,
  );
  if (qStem != null) {
    return AdvisoryTitleGuess(
      title: qStem,
      source: 'stem',
      styleSource: 'stem',
      styledN: styledLines.length,
    );
  }

  return AdvisoryTitleGuess(
    title: '',
    source: 'failed',
    styleSource: 'failed',
    styledN: styledLines.length,
  );
}
