/// design/228 · 230 — weak title heuristic from PDF Info.Title + head text.
library;

import 'doc_role_detect.dart';

final _siLine = RegExp(
  r'^\s*(supplementary\s+(?:information|materials?|data)|supporting\s+information|electronic\s+supplementary)\b',
  caseSensitive: false,
);

/// design/230 — snake enum for evidence (`info` | `head_line` | `stem`).
class AdvisoryTitleGuess {
  const AdvisoryTitleGuess({required this.title, required this.source});

  final String title;

  /// `info` | `head_line` | `stem`
  final String source;
}

bool looksLikePaperTitle(String raw) {
  final t = raw.trim().replaceAll(RegExp(r'\s+'), ' ');
  if (t.length < 12 || t.length > 200) return false;
  if (_siLine.hasMatch(t)) return false;
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
