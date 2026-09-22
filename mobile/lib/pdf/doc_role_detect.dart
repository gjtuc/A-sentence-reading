/// design/228 · 229 · 235 · 363 — Dart port of supplementary_detect.py (advisory only).
library;

class DocRoleDetectResult {
  const DocRoleDetectResult({
    required this.role,
    required this.reason,
    required this.headLen,
    required this.markerHit,
    required this.filenameSiHint,
    required this.pageLabelHit,
    required this.strippedFormat,
  });

  /// `main` | `supplementary`
  final String role;
  final String reason;
  final int headLen;
  final bool markerHit;
  final bool filenameSiHint;
  final bool pageLabelHit;
  final bool strippedFormat;
}

// design/363 — the cover line, and only as its own line.
final _coverLine = RegExp(
  r'^\s*(?:the\s+)?('
  r'supporting\s+information'
  r'|supporting\s+online\s+materials?'
  r'|supporting\s+materials?'
  r'|supplementary\s+information'
  r'|supplementary\s+materials?'
  r'|electronic\s+supplementary\s+information'
  r')\b',
  caseSensitive: false,
);

final _chromeLine = RegExp(
  r'^\s*('
  r's\s*[-–—]?\s*\d{1,3}'
  r'|access'
  r'|metrics\s*&\s*more'
  r'|article\s+recommendations'
  r'|read\s+online'
  r'|cite\s+this\s*:'
  r'|article'
  r'|research'
  r'|https?://\S+'
  r'|doi:\s*\S+'
  r'|www\.\S+'
  r'|in\s+the\s+format\s+provided\s+by\s+the'
  r'|authors\s+and\s+unedited'
  r')\s*$',
  caseSensitive: false,
);

final _abstractLine = RegExp(
  r'^\s*(abstract|conspectus)\b',
  caseSensitive: false,
);

// design/281 — do NOT match bare "sup"/"supp" inside "supported"/"support".
final _siFilename = RegExp(
  r'(?:^|[/\_.-])(?:'
  r'si(?:[_.=-]|\d|$)'
  r'|mmc\d+'
  r'|moesm\d*'
  r'|esm\d+'
  r'|supp?(?:mat|l(?:ementary)?)(?:[-_.]?\d+)?'
  r'|sup[-_.]?\d+'
  r')'
  r'|supporting[-_ ]?information'
  r'|suppl(?:ementary)?'
  r'|[-_.]som(?:[-_.]|$)',
  caseSensitive: false,
);

final _siPageLabel = RegExp(
  r'(?:^|\n)\s*S\s*[-–—]?\s*\d{1,3}\b',
  caseSensitive: false,
);

const _headChars = 8000;

bool filenameLooksLikeSi(String? filename) {
  final name = (filename ?? '').trim();
  if (name.isEmpty) return false;
  var base = name;
  final slash = base.lastIndexOf('/');
  if (slash >= 0) base = base.substring(slash + 1);
  final bslash = base.lastIndexOf('\\');
  if (bslash >= 0) base = base.substring(bslash + 1);
  return _siFilename.hasMatch(base);
}

({String text, bool stripped}) stripFormatChars(String text) {
  final out = StringBuffer();
  var stripped = false;
  for (final rune in text.runes) {
    final ch = String.fromCharCode(rune);
    if (ch == '\n' || ch == '\r' || ch == '\t') {
      out.write(ch);
      continue;
    }
    if (ch == '\ufeff' ||
        ch == '\u200b' ||
        ch == '\u200c' ||
        ch == '\u200d' ||
        ch == '\u2060' ||
        (rune < 0x20) ||
        (rune >= 0x7f && rune <= 0x9f) ||
        (rune >= 0x200B && rune <= 0x200F) ||
        (rune >= 0x202A && rune <= 0x202E) ||
        (rune >= 0x2060 && rune <= 0x2064) ||
        rune == 0xFEFF) {
      stripped = true;
      continue;
    }
    out.write(ch);
  }
  return (text: out.toString(), stripped: stripped);
}

String normalizeDocRole(String? raw) {
  final v = (raw ?? '').trim().toLowerCase();
  if (v == 'supplementary' || v == 'si' || v == 'supp') {
    return 'supplementary';
  }
  return 'main';
}

bool _isChromeLine(String line) {
  final s = line.trim();
  if (s.isEmpty) return true;
  if (s.length <= 2) return true;
  if (_chromeLine.hasMatch(s)) return true;
  if (RegExp(r'^s[iı]$', caseSensitive: false).hasMatch(s)) return true;
  if (RegExp(r'^cite\s+this\b', caseSensitive: false).hasMatch(s)) return true;
  return false;
}

bool coverPhraseAboveTitle(String text) {
  var coverSeen = false;
  for (final raw in text.split('\n')) {
    if (_isChromeLine(raw)) continue;
    if (_coverLine.hasMatch(raw)) {
      coverSeen = true;
      continue;
    }
    if (_abstractLine.hasMatch(raw)) return false;
    return coverSeen;
  }
  return coverSeen;
}

DocRoleDetectResult detectDocRoleDetailed(
  String text, {
  String? filename,
}) {
  final strippedPair = stripFormatChars(text);
  final cleaned = strippedPair.text;
  final stripped = strippedPair.stripped;
  final head = cleaned.length <= _headChars
      ? cleaned
      : cleaned.substring(0, _headChars);
  final headLen = head.length;
  final fnHint = filenameLooksLikeSi(filename);
  final pageLabel = headLen > 0
      ? _siPageLabel.hasMatch(
          head.length <= 1200 ? head : head.substring(0, 1200),
        )
      : false;
  final coverHit = headLen > 0 && coverPhraseAboveTitle(head);
  if (head.trim().isEmpty) {
    // design/280 — Info.Title may still yield a title while extract text is empty.
    if (fnHint) {
      return DocRoleDetectResult(
        role: 'supplementary',
        reason: 'filename_si',
        headLen: 0,
        markerHit: false,
        filenameSiHint: true,
        pageLabelHit: false,
        strippedFormat: stripped,
      );
    }
    return DocRoleDetectResult(
      role: 'main',
      reason: 'empty_head',
      headLen: 0,
      markerHit: false,
      filenameSiHint: fnHint,
      pageLabelHit: false,
      strippedFormat: stripped,
    );
  }
  // design/363 — either signal is enough. Filename first so a Nature SI whose
  // cover line sits under the reprinted title is still SI.
  if (fnHint) {
    return DocRoleDetectResult(
      role: 'supplementary',
      reason: 'filename_si',
      headLen: headLen,
      markerHit: coverHit,
      filenameSiHint: true,
      pageLabelHit: pageLabel,
      strippedFormat: stripped,
    );
  }
  if (coverHit) {
    return DocRoleDetectResult(
      role: 'supplementary',
      reason: 'cover_above_title',
      headLen: headLen,
      markerHit: true,
      filenameSiHint: false,
      pageLabelHit: pageLabel,
      strippedFormat: stripped,
    );
  }
  return DocRoleDetectResult(
    role: 'main',
    reason: 'default_main',
    headLen: headLen,
    markerHit: false,
    filenameSiHint: false,
    pageLabelHit: pageLabel,
    strippedFormat: stripped,
  );
}
