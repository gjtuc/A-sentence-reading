/// design/228 · 229 · 235 — Dart port of supplementary_detect.py (advisory only).
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
  r'(?:^|[/\_.-])(?:si(?:[_.=-]|\d|$)|mmc\d*|moesm\d*|esm\d*|sup(?:p)?(?:mat|-?\d+)?)|supporting[-_ ]?information|suppl(?:ementary)?',
  caseSensitive: false,
);

final _siPageLabel = RegExp(
  r'(?:^|\n)\s*S\s*[-–—]?\s*\d{1,3}\b',
  caseSensitive: false,
);

// design/255 — Table S1, Figure S1, Scheme S1 in SI head
final _siTableFig = RegExp(
  r'\b(?:Table|Fig(?:ure)?|Scheme)\s*S\d+\b',
  caseSensitive: false,
);

// design/229 — ACS article chrome near Supporting Information badge.
final _acsChrome = <RegExp>[
  RegExp(r'(?:^|\n)\s*ACCESS\b', caseSensitive: false),
  RegExp(r'Metrics\s*&\s*More', caseSensitive: false),
  RegExp(r'Article\s+Recommendations', caseSensitive: false),
  RegExp(r'(?:^|\n)\s*s[iı]\b', caseSensitive: false),
];

// design/229 · 235 — ABSTRACT or CONSPECTUS soon after SI badge.
final _abstractSoon = RegExp(
  r'(?:ABSTRACT\s*:|(?:^|\n)\s*ABSTRACT\b|CONSPECTUS\s*:|(?:^|\n)\s*CONSPECTUS\b)',
  caseSensitive: false,
);

// design/235 — RSC ESI availability footnote (not ESI cover).
final _esiAvailableFootnote = RegExp(
  r'(?:[†*‡]\s*)?Electronic\s+supplementary\s+information'
  r'(?:\s*\(\s*ESI\s*\))?\s+available\b',
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

bool _isAcsMainSiBadge(String head, RegExpMatch match) {
  final start = match.start - 400 < 0 ? 0 : match.start - 400;
  final end = match.end + 250 > head.length ? head.length : match.end + 250;
  final window = head.substring(start, end);
  var chromeHits = 0;
  for (final pat in _acsChrome) {
    if (pat.hasMatch(window)) chromeHits++;
  }
  final afterEnd =
      match.end + 300 > head.length ? head.length : match.end + 300;
  final after = head.substring(match.end, afterEnd);
  final abstractSoon = _abstractSoon.hasMatch(after);
  return chromeHits >= 2 && abstractSoon;
}

bool _isEsiAvailabilityFootnote(String head, RegExpMatch match) {
  final start = match.start - 80 < 0 ? 0 : match.start - 80;
  final end = match.end + 160 > head.length ? head.length : match.end + 160;
  return _esiAvailableFootnote.hasMatch(head.substring(start, end));
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
  final markerMatch = headLen > 0 ? _siHead.firstMatch(head) : null;
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
  if (markerMatch != null) {
    if (_isAcsMainSiBadge(head, markerMatch)) {
      return DocRoleDetectResult(
        role: 'main',
        reason: 'head_marker_acs_chrome_veto',
        headLen: headLen,
        markerHit: true,
        filenameSiHint: fnHint,
        pageLabelHit: pageLabel,
        strippedFormat: stripped,
      );
    }
    if (_isEsiAvailabilityFootnote(head, markerMatch)) {
      return DocRoleDetectResult(
        role: 'main',
        reason: 'head_marker_esi_footnote_veto',
        headLen: headLen,
        markerHit: true,
        filenameSiHint: fnHint,
        pageLabelHit: pageLabel,
        strippedFormat: stripped,
      );
    }
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
  final isDocx = (filename ?? '').trim().toLowerCase().endsWith('.docx');
  final tableFigHit = headLen > 0 && _siTableFig.hasMatch(head);

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
  if (fnHint && isDocx) {
    return DocRoleDetectResult(
      role: 'supplementary',
      reason: 'filename_si_and_docx',
      headLen: headLen,
      markerHit: false,
      filenameSiHint: true,
      pageLabelHit: pageLabel,
      strippedFormat: stripped,
    );
  }
  if (fnHint && tableFigHit) {
    return DocRoleDetectResult(
      role: 'supplementary',
      reason: 'filename_si_and_table_fig',
      headLen: headLen,
      markerHit: false,
      filenameSiHint: true,
      pageLabelHit: pageLabel,
      strippedFormat: stripped,
    );
  }
  if (tableFigHit && pageLabel) {
    return DocRoleDetectResult(
      role: 'supplementary',
      reason: 'table_fig_and_page_label',
      headLen: headLen,
      markerHit: false,
      filenameSiHint: fnHint,
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
