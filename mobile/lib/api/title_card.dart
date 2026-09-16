import 'reading_models.dart';

/// Title card must match the picked session title. Chrome cards lose their KO line.
String titleCardToken(List<SentenceView> sentences, String pickedTitle) {
  final picked = _norm(pickedTitle);
  final hasTitle = sentences.any((s) => s.section == 'title');
  if (!_titleUsable(picked)) return hasTitle ? 'kept' : 'absent';
  var seen = false;
  var card = 'absent';
  for (final s in sentences) {
    if (s.section != 'title') continue;
    if (seen) {
      card = 'replaced';
      continue;
    }
    seen = true;
    card = _norm(s.text) == picked ? 'kept' : 'replaced';
  }
  return card;
}

List<SentenceView> alignTitleSentences(
  List<SentenceView> sentences,
  String pickedTitle,
) {
  final picked = _norm(pickedTitle);
  if (!_titleUsable(picked)) return sentences;
  final out = <SentenceView>[];
  var keptOne = false;
  for (final s in sentences) {
    if (s.section != 'title') {
      out.add(s);
      continue;
    }
    if (keptOne) continue;
    keptOne = true;
    if (_norm(s.text) == picked) {
      out.add(s);
      continue;
    }
    out.add(
      SentenceView(
        id: s.id.isEmpty ? 'sent_title' : s.id,
        text: picked,
        section: 'title',
        qualityFlags: s.qualityFlags,
      ),
    );
  }
  return out;
}

String _norm(String raw) => raw.replaceAll(RegExp(r'\s+'), ' ').trim();

bool _titleUsable(String text) {
  if (text.length < 12 || text.length > 350) return false;
  if (RegExp(r'^1-s2\.0-S\d', caseSensitive: false).hasMatch(text)) return false;
  if (RegExp(
    r'\b(?:abstract|a\s+b\s+s\s+t\s+r\s+a\s+c\s+t|article\s+info|keywords)\b',
    caseSensitive: false,
  ).hasMatch(text)) {
    return false;
  }
  if (RegExp(
    r'^(?:key laboratory|school of|department of|university of|corresponding author|email\s*:)',
    caseSensitive: false,
  ).hasMatch(text)) {
    return false;
  }
  final commas = ','.allMatches(text).length;
  final stars = '*'.allMatches(text).length;
  if (stars >= 1 && commas >= 2) return false;
  if (commas >= 3 &&
      !RegExp(
        r'\b(of|for|with|from|over|via|using|toward|towards)\b',
        caseSensitive: false,
      ).hasMatch(text)) {
    return false;
  }
  return true;
}
