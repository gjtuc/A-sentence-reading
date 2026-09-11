/// design/228 · 230 · 233 · 236 — weak title heuristic from PDF Info.Title + head text.
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
  r'|green chemical engineering'
  r'|scientific reports'
  r'|sustainable energy\s*(?:&|and)?\s*fuels'
  r'|applied physics'
  r'|chem\.?\s*eng\.?\s*j'
  r')',
  caseSensitive: false,
);

/// design/230 — snake enum for evidence (`info` | `head_line` | `stem`).
class AdvisoryTitleGuess {
  const AdvisoryTitleGuess({required this.title, required this.source});

  final String title;

  /// `info` | `head_line` | `stem`
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

bool looksLikePaperTitle(String raw) {
  final t = raw.trim().replaceAll(RegExp(r'\s+'), ' ');
  if (t.length < 12 || t.length > 200) return false;
  if (_siLine.hasMatch(t)) return false;
  if (isAdvisoryTitleChrome(t)) return false;
  if (RegExp(r'^[\d\W_]+$').hasMatch(t)) return false;
  final digits = t.replaceAll(RegExp(r'\D'), '').length;
  if (digits > t.length * 0.5) return false;
  return true;
}

String stemFromDisplayName(String displayName) {
  var n = displayName.trim();
  if (n.toLowerCase().endsWith('.pdf')) {
    n = n.substring(0, n.length - 4);
  }
  try {
    n = Uri.decodeComponent(n);
  } catch (_) {}
  return n.trim();
}

AdvisoryTitleGuess guessAdvisoryTitle({
  required String infoTitle,
  required String headText,
  required String displayName,
}) {
  final info = infoTitle.trim();
  if (looksLikePaperTitle(info)) {
    return AdvisoryTitleGuess(
      title: info.replaceAll(RegExp(r'\s+'), ' '),
      source: 'info',
    );
  }

  final cleaned = stripFormatChars(headText).text;
  for (final line in cleaned.split(RegExp(r'[\r\n]+'))) {
    final t = line.trim().replaceAll(RegExp(r'\s+'), ' ');
    if (t.isEmpty) continue;
    if (_siLine.hasMatch(t)) continue;
    if (isAdvisoryTitleChrome(t)) continue;
    if (t.length < 12) continue;
    if (looksLikePaperTitle(t)) {
      return AdvisoryTitleGuess(title: t, source: 'head_line');
    }
  }
  return AdvisoryTitleGuess(
    title: stemFromDisplayName(displayName),
    source: 'stem',
  );
}
