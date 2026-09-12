/// design/251 — mate-fetch validation (magic / size / host allowlist).
library;

const int kMateFetchMaxBytes = 50 * 1024 * 1024;
const int kMateFetchMaxRedirects = 5;

/// Hosts we will GET PDF/ZIP bytes from (OA + known SI templates). Empty host → reject.
const Set<String> kMateFetchHostAllowlist = {
  'api.unpaywall.org',
  'pubs.acs.org',
  'www.rsc.org',
  'pubs.rsc.org',
  'www.nature.com',
  'static-content.springer.com',
  'link.springer.com',
  'onlinelibrary.wiley.com',
  'api.wiley.com',
  'iopscience.iop.org',
  'cdn.iopscience.iop.org',
  'arxiv.org',
  'export.arxiv.org',
  'europepmc.org',
  'www.ncbi.nlm.nih.gov',
  'pmc.ncbi.nlm.nih.gov',
  'pdfs.semanticscholar.org',
  'www.biorxiv.org',
  'www.medrxiv.org',
  'chemrxiv.org',
};

bool mateHostAllowed(String host) {
  final h = host.trim().toLowerCase();
  if (h.isEmpty) return false;
  if (kMateFetchHostAllowlist.contains(h)) return true;
  // Unpaywall OA often lands on publisher CDNs / institutional repos.
  for (final allowed in kMateFetchHostAllowlist) {
    if (h == allowed || h.endsWith('.$allowed')) return true;
  }
  // Common OA mirrors (still not Sci-Hub).
  if (h.endsWith('.ac.uk') ||
      h.endsWith('.edu') ||
      h.endsWith('.gov') ||
      h.contains('openaccess') ||
      h.contains('repository') ||
      h.endsWith('.arxiv.org')) {
    return true;
  }
  return false;
}

enum MateValidateCode {
  ok,
  empty,
  tooLarge,
  notPdf,
  html,
  badHost,
}

class MateValidateResult {
  const MateValidateResult({
    required this.code,
    this.size = 0,
  });

  final MateValidateCode code;
  final int size;

  bool get ok => code == MateValidateCode.ok;
}

MateValidateResult validateMateBytes(
  List<int> bytes, {
  int maxBytes = kMateFetchMaxBytes,
}) {
  if (bytes.isEmpty) {
    return const MateValidateResult(code: MateValidateCode.empty);
  }
  if (bytes.length > maxBytes) {
    return MateValidateResult(code: MateValidateCode.tooLarge, size: bytes.length);
  }
  final head = bytes.length >= 16 ? bytes.sublist(0, 16) : bytes;
  // %PDF
  if (head.length >= 4 &&
      head[0] == 0x25 &&
      head[1] == 0x50 &&
      head[2] == 0x44 &&
      head[3] == 0x46) {
    return MateValidateResult(code: MateValidateCode.ok, size: bytes.length);
  }
  // ZIP (SI sometimes zip) — PK
  if (head.length >= 2 && head[0] == 0x50 && head[1] == 0x4b) {
    return MateValidateResult(code: MateValidateCode.ok, size: bytes.length);
  }
  final asText = String.fromCharCodes(
    head.where((b) => b >= 9 && b < 128),
  ).toLowerCase();
  if (asText.contains('<!doctype') ||
      asText.contains('<html') ||
      asText.contains('<head')) {
    return MateValidateResult(code: MateValidateCode.html, size: bytes.length);
  }
  return MateValidateResult(code: MateValidateCode.notPdf, size: bytes.length);
}

String sizeBucket(int n) {
  if (n < 100 * 1024) return 'lt_100kb';
  if (n < 1024 * 1024) return 'lt_1mb';
  if (n < 5 * 1024 * 1024) return 'lt_5mb';
  if (n < 20 * 1024 * 1024) return 'lt_20mb';
  return 'ge_20mb';
}


/// design/252 — snake token for evidence (never CamelCase enum .name).
String mateValidateCodeSnake(MateValidateCode code) {
  switch (code) {
    case MateValidateCode.ok:
      return 'ok';
    case MateValidateCode.empty:
      return 'empty';
    case MateValidateCode.tooLarge:
      return 'too_large';
    case MateValidateCode.notPdf:
      return 'not_pdf';
    case MateValidateCode.html:
      return 'html';
    case MateValidateCode.badHost:
      return 'bad_host';
  }
}
