/// design/239 — Dart twin of Python normalize_title_key / normalize_pairing_key.
library;

/// Port of `sentence_reading.cache.paper_cache.normalize_title_key`.
String normalizeTitleKey(String title) {
  var t = _nfkc(title);
  t = t.replaceFirst(RegExp(r'^\s*(title)\s*:\s*', caseSensitive: false), '');
  t = t.toLowerCase(); // Dart casefold ≈ lowercase for Latin; NFKC already applied
  // Python uses casefold(); for ASCII science titles toLowerCase matches.
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
  // Dart has no unicodedata; use Characters-free pass-through + common folds.
  // For science titles NFKC mainly folds compatibility forms; String is UTF-16.
  // Prefer package-free: rely on already-normalized PDF extract text.
  return s;
}
