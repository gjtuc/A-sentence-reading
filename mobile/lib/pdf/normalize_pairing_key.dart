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

/// design/265 — reject stem keys like `1` / `2` that false-pair unrelated PDFs.
bool isUsablePairingKey(String key) {
  final k = key.trim().toLowerCase();
  if (k.isEmpty) return false;
  if (k.startsWith('doi:') && k.length > 8) return true;
  if (k.startsWith('acs:') && k.length > 7) return true;
  if (k.length < 12) return false;
  // Bare ACS-like code without soft-pair prefix — too weak alone.
  if (RegExp(r'^[a-z]{1,4}\d[a-z0-9]*$').hasMatch(k)) return false;
  return true;
}

/// Title pairing allows at most this many character edits.
const int kPairingTypoMax = 5;

int pairingEditDistance(String a, String b, {int max = kPairingTypoMax}) {
  if (a == b) return 0;
  if (a.isEmpty || b.isEmpty) return max + 1;
  if ((a.length - b.length).abs() > max) return max + 1;
  var prev = List<int>.generate(b.length + 1, (i) => i);
  var cur = List<int>.filled(b.length + 1, 0);
  for (var i = 1; i <= a.length; i++) {
    cur[0] = i;
    var rowMin = cur[0];
    for (var j = 1; j <= b.length; j++) {
      final cost = a.codeUnitAt(i - 1) == b.codeUnitAt(j - 1) ? 0 : 1;
      final del = prev[j] + 1;
      final ins = cur[j - 1] + 1;
      final sub = prev[j - 1] + cost;
      var best = del < ins ? del : ins;
      if (sub < best) best = sub;
      cur[j] = best;
      if (best < rowMin) rowMin = best;
    }
    if (rowMin > max) return max + 1;
    final swap = prev;
    prev = cur;
    cur = swap;
  }
  return prev[b.length];
}

bool pairingKeysWithinTypos(String a, String b, {int max = kPairingTypoMax}) {
  final left = a.trim().toLowerCase();
  final right = b.trim().toLowerCase();
  if (!isUsablePairingKey(left) || !isUsablePairingKey(right)) return false;
  return pairingEditDistance(left, right, max: max) <= max;
}

/// design/265 — ACS manuscript id from filename stem (an1c00673, am2c04149, …).
String? acsManuscriptIdFromDisplayName(String displayName) {
  var n = displayName.trim();
  if (n.toLowerCase().endsWith('.pdf')) {
    n = n.substring(0, n.length - 4);
  } else if (n.toLowerCase().endsWith('.docx')) {
    n = n.substring(0, n.length - 5);
  }
  try {
    n = Uri.decodeComponent(n);
  } catch (_) {}
  n = n.replaceAll(RegExp(r'[_\s-]+'), ' ').trim().toLowerCase();
  final m = RegExp(r'\b([a-z]{1,4}\d[a-z0-9]{4,})\b').firstMatch(n);
  if (m == null) return null;
  return m.group(1);
}

/// design/265 — DOI soft-pair token (lowercase, no URL chrome).
String? doiPairingKey(String doi) {
  var d = doi.trim().toLowerCase();
  if (d.isEmpty) return null;
  d = d.replaceFirst(RegExp(r'^https?://(dx\.)?doi\.org/'), '');
  d = d.replaceFirst(RegExp(r'^doi:\s*'), '');
  d = d.trim();
  if (d.length < 8 || !d.contains('/')) return null;
  return 'doi:$d';
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
