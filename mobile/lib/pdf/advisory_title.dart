/// design/228 — weak title heuristic from PDF Info.Title + head text.
library;

import 'doc_role_detect.dart';

final _siLine = RegExp(
  r'^\s*(supplementary\s+(?:information|materials?|data)|supporting\s+information|electronic\s+supplementary)\b',
  caseSensitive: false,
);

bool looksLikePaperTitle(String raw) {
  final t = raw.trim().replaceAll(RegExp(r'\s+'), ' ');
  if (t.length < 12 || t.length > 200) return false;
  if (_siLine.hasMatch(t)) return false;
  if (RegExp(r'^[\d\W_]+$').hasMatch(t)) return false;
  // Mostly digits
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

String guessAdvisoryTitle({
  required String infoTitle,
  required String headText,
  required String displayName,
}) {
  final info = infoTitle.trim();
  if (looksLikePaperTitle(info)) return info.replaceAll(RegExp(r'\s+'), ' ');

  final cleaned = stripFormatChars(headText).text;
  for (final line in cleaned.split(RegExp(r'[\r\n]+'))) {
    final t = line.trim().replaceAll(RegExp(r'\s+'), ' ');
    if (t.isEmpty) continue;
    if (_siLine.hasMatch(t)) continue;
    if (t.length < 12) continue;
    if (looksLikePaperTitle(t)) return t;
  }
  return stemFromDisplayName(displayName);
}
