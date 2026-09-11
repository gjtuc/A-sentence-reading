/// design/228 — Dart port of supplementary_detect.py (advisory only).
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

final _siHead = RegExp(
  r'(?:^|\n)\s*('
  r'supplementary\s+(?:information|materials?|data)'
  r'|supporting\s+information'
  r'|electronic\s+supplementary'
  r'|esi\b'
  r')',
  caseSensitive: false,
);

final _siFilename = RegExp(
  r'(?:^|[/\\_.-])si(?:[_.=-]|\d)|supporting[-_ ]?information|suppl(?:ementary)?',
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
  final marker = headLen > 0 ? _siHead.hasMatch(head) : false;

  if (head.trim().isEmpty) {
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
  if (marker) {
    return DocRoleDetectResult(
      role: 'supplementary',
      reason: 'head_marker',
      headLen: headLen,
      markerHit: true,
      filenameSiHint: fnHint,
      pageLabelHit: pageLabel,
      strippedFormat: stripped,
    );
  }
  if (fnHint && pageLabel) {
    return DocRoleDetectResult(
      role: 'supplementary',
      reason: 'filename_si_and_page_label',
      headLen: headLen,
      markerHit: false,
      filenameSiHint: true,
      pageLabelHit: true,
      strippedFormat: stripped,
    );
  }
  return DocRoleDetectResult(
    role: 'main',
    reason: 'default_main',
    headLen: headLen,
    markerHit: false,
    filenameSiHint: fnHint,
    pageLabelHit: pageLabel,
    strippedFormat: stripped,
  );
}
