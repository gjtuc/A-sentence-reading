/// design/228 · 230 · 233 · 236 · 265 — weak title heuristic from PDF Info.Title + head text.
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
  r'|@\w+\.\w+'
  r'|orcid'
  r'|^\S+\s+\S+,\s*\S+.*university'
  r')',
  caseSensitive: false,
);

/// design/230 · 265 — snake enum for evidence (`info` | `head_line` | `stem` | `failed`).
class AdvisoryTitleGuess {
  const AdvisoryTitleGuess({required this.title, required this.source});

  final String title;

  /// `info` | `head_line` | `stem` | `failed`
  final String source;
}

bool isAdvisoryTitleChrome(String raw) {
  final t = raw.trim().replaceAll(RegExp(r'\s+'), ' ');
  if (t.isEmpty) return true;
  if (_exactChrome.hasMatch(t)) return true;
  if (_prefixChrome.hasMatch(t)) return true;
  if (_journalChrome.hasMatch(t)) return true;
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

/// design/265 — Info.Title cut mid-phrase (publisher truncation).
bool isTruncatedInfoTitle(String raw) {
  final t = decodeHtmlEntities(raw).trim();
  if (t.length < 20) return false;
  if (t.endsWith('-') || t.endsWith(',') || t.endsWith(':')) return true;
  if (_danglingEnd.hasMatch(t)) return true;
  // Ends with a short lowercase token that looks mid-word cut ("The", "Functio").
  final parts = t.split(RegExp(r'\s+'));
  if (parts.isEmpty) return false;
  final last = parts.last;
  if (last.length >= 3 &&
      last.length <= 12 &&
      RegExp(r'^[A-Z][a-z]+$').hasMatch(last) &&
      !RegExp(
        r'^(Study|Review|Catalysts?|Methane|Oxide|Carbon|Energy|Water|Hydrogen)$',
        caseSensitive: false,
      ).hasMatch(last)) {
    // Single capitalized dangling word after a long title often = cut.
    if (parts.length >= 6) return true;
  }
  return false;
}

/// design/265 — ACS manuscript id dumped into Info.Title.
bool isCodeLikeInfoTitle(String raw) {
  final t = decodeHtmlEntities(raw).trim();
  if (t.isEmpty) return false;
  if (_acsCodeInfo.hasMatch(t)) return true;
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
  if (RegExp(r'^[\d\W_]+$').hasMatch(t)) return false;
  final digits = t.replaceAll(RegExp(r'\D'), '').length;
  if (digits > t.length * 0.5) return false;
  return true;
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
  // Drop trailing __1_ / _1 style suffixes before judging stem quality.
  n = n.replaceAll(RegExp(r'[_\s-]+$'), '');
  n = n.replaceFirst(RegExp(r'[_\s-]+\d{1,2}$'), '');
  return decodeHtmlEntities(n);
}

AdvisoryTitleGuess guessAdvisoryTitle({
  required String infoTitle,
  required String headText,
  required String displayName,
}) {
  final qInfo = qualifyAdvisoryTitleCandidate(
    infoTitle,
    rejectTruncated: true,
  );
  if (qInfo != null) {
    return AdvisoryTitleGuess(title: qInfo, source: 'info');
  }

  final rawHead = stripFormatChars(headText).text;
  for (final line in rawHead.split(RegExp(r'[\r\n]+'))) {
    final t = decodeHtmlEntities(line);
    if (t.isEmpty) continue;
    if (_siLine.hasMatch(t)) continue;
    if (isAdvisoryTitleChrome(t)) continue;
    if (looksLikeAffiliationOrCaption(t)) continue;
    if (t.length < 12) continue;
    final q = qualifyAdvisoryTitleCandidate(t);
    if (q != null) {
      return AdvisoryTitleGuess(title: q, source: 'head_line');
    }
  }

  final stem = stemFromDisplayName(displayName);
  final qStem = qualifyAdvisoryTitleCandidate(
    stem,
    rejectLowQualityStem: true,
  );
  if (qStem != null) {
    return AdvisoryTitleGuess(title: qStem, source: 'stem');
  }

  return const AdvisoryTitleGuess(title: '', source: 'failed');
}
