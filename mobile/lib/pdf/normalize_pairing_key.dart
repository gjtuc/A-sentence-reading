/// design/239 - Dart twin of Python normalize_title_key / normalize_pairing_key.
library;

/// Port of `sentence_reading.cache.paper_cache.normalize_title_key`.
String normalizeTitleKey(String title) {
  var t = _nfkc(title);
  t = t.replaceFirst(RegExp(r'\s*(title)\s*:\s*', caseSensitive: false), '');
  t = t.toLowerCase();
  t = t.replaceAll(RegExp(r'[^\w\s]+', unicode: true), ' ');
  t = t.replaceAll(RegExp(r'\s+'), ' ').trim();
  return t;
}

/// Port of `sentence_reading.cache.paper_cache.normalize_pairing_key` (design/218).
String normalizePairingKey(String title) {
  var t = normalizeTitleKey(title);
  if (t.isEmpty) return '';
  t = t.replaceFirst(
    RegExp(
      r'^(?:supporting|supplementary)\s+(?:information|materials?|data)\s*',
    ),
    '',
  );
  t = t.replaceAll(RegExp(r'\b(a|an|the)\b'), ' ');
  t = t.replaceAll(RegExp(r'\s+'), ' ').trim();
  return t;
}

String _nfkc(String s) {
  // Dart has no unicodedata; fold common compatibility forms (design/239).
  // Prefer Android Normalizer.NFKC via SAF channel when available for advisory.
  if (s.isEmpty) return s;
  final buf = StringBuffer();
  for (final r in s.runes) {
    if (r >= 0xFF21 && r <= 0xFF3A) {
      buf.writeCharCode(r - 0xFF21 + 0x41);
    } else if (r >= 0xFF41 && r <= 0xFF5A) {
      buf.writeCharCode(r - 0xFF41 + 0x61);
    } else if (r >= 0xFF10 && r <= 0xFF19) {
      buf.writeCharCode(r - 0xFF10 + 0x30);
    } else if (r == 0x2013 || r == 0x2014 || r == 0x2212) {
      buf.write('-');
    } else if (r == 0x2018 || r == 0x2019 || r == 0x201B) {
      buf.write("'");
    } else if (r == 0x201C || r == 0x201D || r == 0x201F) {
      buf.write('"');
    } else if (r == 0x00A0 || r == 0x202F || r == 0x2009) {
      buf.write(' ');
    } else if (r == 0xFB01) {
      buf.write('fi');
    } else if (r == 0xFB02) {
      buf.write('fl');
    } else {
      buf.writeCharCode(r);
    }
  }
  return buf.toString();
}
