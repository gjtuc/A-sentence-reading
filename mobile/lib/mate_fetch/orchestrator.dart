/// design/251 Phase A — mate-fetch orchestrator (T0/T1/T3 meta/T4).
library;

import 'dart:typed_data';

import 'fetch.dart';
import 'validate.dart';

class MateCandidate {
  const MateCandidate({
    required this.tier,
    required this.source,
    required this.url,
    this.kind = 'pdf',
    this.host = '',
    this.license = '',
  });

  final String tier;
  final String source;
  final String url;
  final String kind;
  final String host;
  final String license;

  factory MateCandidate.fromJson(Map<String, dynamic> json) {
    return MateCandidate(
      tier: '${json['tier'] ?? ''}'.trim(),
      source: '${json['source'] ?? ''}'.trim(),
      url: '${json['url'] ?? ''}'.trim(),
      kind: '${json['kind'] ?? 'pdf'}'.trim().isEmpty
          ? 'pdf'
          : '${json['kind']}'.trim(),
      host: '${json['host'] ?? ''}'.trim(),
      license: '${json['license'] ?? ''}'.trim(),
    );
  }
}

class MateResolveMeta {
  const MateResolveMeta({
    required this.ok,
    this.enabled = true,
    this.candidates = const [],
    this.fallbackBrowser = '',
    this.siStatus = 'unknown',
    this.error = '',
  });

  final bool ok;
  final bool enabled;
  final List<MateCandidate> candidates;
  final String fallbackBrowser;
  final String siStatus;
  final String error;

  factory MateResolveMeta.fromJson(Map<String, dynamic> json) {
    final raw = json['candidates'];
    final list = <MateCandidate>[];
    if (raw is List) {
      for (final e in raw) {
        if (e is Map) {
          list.add(MateCandidate.fromJson(Map<String, dynamic>.from(e)));
        }
      }
    }
    final si = '${json['si_status'] ?? 'unknown'}'.trim().toLowerCase();
    return MateResolveMeta(
      ok: json['ok'] == true,
      enabled: json.containsKey('enabled') ? json['enabled'] == true : true,
      candidates: list,
      fallbackBrowser: '${json['fallback_browser'] ?? ''}'.trim(),
      siStatus: (si == 'absent' || si == 'available' || si == 'unknown')
          ? si
          : 'unknown',
      error: '${json['error'] ?? ''}'.trim(),
    );
  }
}

enum MateOrchestrateMode {
  fetched,
  absent,
  fallbackBrowser,
  killed,
  failed,
}

class MateOrchestrateResult {
  const MateOrchestrateResult({
    required this.mode,
    this.bytes,
    this.filename = '',
    this.tier = '',
    this.source = '',
    this.browserUrl = '',
    this.siStatus = 'unknown',
    this.code = '',
  });

  final MateOrchestrateMode mode;
  final Uint8List? bytes;
  final String filename;
  final String tier;
  final String source;
  final String browserUrl;
  final String siStatus;
  final String code;
}

String mateFilenameFor({
  required String doi,
  required String want,
  String source = '',
}) {
  final safe = doi.replaceAll(RegExp(r'[^A-Za-z0-9._-]+'), '_');
  if (want == 'si') {
    final stem = source.isNotEmpty ? source : 'si';
    return '${safe}_$stem.pdf';
  }
  return '$safe.pdf';
}

/// Try PDF candidates in order; fall back to browser URL.
Future<MateOrchestrateResult> orchestrateMateFetch({
  required MateResolveMeta meta,
  required String doi,
  required String want,
  required Future<MateFetchOutcome> Function(String url) fetchBytes,
  bool matePresent = false,
}) async {
  if (matePresent) {
    return const MateOrchestrateResult(
      mode: MateOrchestrateMode.failed,
      code: 'mate_present',
    );
  }
  if (!meta.enabled) {
    final fb = meta.fallbackBrowser.isNotEmpty
        ? meta.fallbackBrowser
        : 'https://doi.org/$doi';
    return MateOrchestrateResult(
      mode: MateOrchestrateMode.killed,
      browserUrl: fb,
      siStatus: meta.siStatus,
      code: 'killed',
    );
  }
  if (want == 'si' && meta.siStatus == 'absent') {
    return MateOrchestrateResult(
      mode: MateOrchestrateMode.absent,
      siStatus: 'absent',
      code: 'si_absent',
    );
  }

  for (final c in meta.candidates) {
    if (c.kind != 'pdf' || c.url.isEmpty) continue;
    final host = c.host.isNotEmpty
        ? c.host
        : (Uri.tryParse(c.url)?.host ?? '');
    if (host.isNotEmpty && !mateHostAllowed(host)) continue;
    final got = await fetchBytes(c.url);
    if (!got.ok || got.bytes == null) continue;
    return MateOrchestrateResult(
      mode: MateOrchestrateMode.fetched,
      bytes: got.bytes,
      filename: mateFilenameFor(doi: doi, want: want, source: c.source),
      tier: c.tier.isEmpty ? 'oa' : c.tier,
      source: c.source,
      siStatus: meta.siStatus,
      code: 'ok',
    );
  }

  final fb = meta.fallbackBrowser.isNotEmpty
      ? meta.fallbackBrowser
      : 'https://doi.org/$doi';
  return MateOrchestrateResult(
    mode: MateOrchestrateMode.fallbackBrowser,
    browserUrl: fb,
    siStatus: meta.siStatus,
    code: 'fallback',
  );
}
