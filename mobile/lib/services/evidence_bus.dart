/// design/169 — client Agent Evidence Bus (ring + batch flush; no UI).
///
/// Failures on evidence POST must not recurse into [record].
library;

import 'dart:async';
import 'dart:math';

import '../api/client.dart';
import '../config.dart';
import 'evidence_kinds.dart';

/// Process-wide bus (bound from [SentenceReadingApp] / tests).
EvidenceBus? asrEvidenceBus;

class EvidenceBus {
  EvidenceBus({
    AsrClient? client,
    this.maxRing = 200,
    this.maxBatch = 50,
    this.flushEvery = const Duration(seconds: 5),
  }) : _client = client;

  AsrClient? _client;
  final int maxRing;
  final int maxBatch;
  final Duration flushEvery;

  bool _enabled = false;
  bool _flushing = false;
  final List<Map<String, dynamic>> _ring = [];
  Timer? _timer;
  String _traceId = '';
  String _sessionId = '';

  void attachClient(AsrClient client) {
    _client = client;
  }

  /// Kill via `/api/status` `evidence_bus` (missing → off fail-closed).
  void setEnabled(bool enabled) {
    _enabled = enabled;
    if (_enabled) {
      _ensureTrace();
      _timer ??= Timer.periodic(flushEvery, (_) => unawaited(flush()));
    } else {
      _timer?.cancel();
      _timer = null;
    }
  }

  bool get enabled => _enabled;

  String get traceId {
    _ensureTrace();
    return _traceId;
  }

  void _ensureTrace() {
    if (_traceId.isNotEmpty) return;
    final r = Random.secure();
    final buf = StringBuffer('tr_');
    for (var i = 0; i < 16; i++) {
      buf.write(r.nextInt(16).toRadixString(16));
    }
    _traceId = buf.toString();
    final ses = StringBuffer('ses_');
    for (var i = 0; i < 12; i++) {
      ses.write(r.nextInt(16).toRadixString(16));
    }
    _sessionId = ses.toString();
  }

  /// Enqueue one event. Dropped when kind not allowlisted or bus off.
  void record(
    String kind, {
    String severity = 'boundary',
    String stage = '',
    String message = '',
    String route = '',
    String jobId = '',
    String cacheId = '',
    int? percent,
    int? httpStatus,
    bool? ok,
    String code = '',
    Map<String, Object?> details = const {},
  }) {
    if (!_enabled) return;
    final k = kind.trim().toLowerCase();
    if (k.isEmpty || !kEvidenceAllowedKinds.contains(k)) return;
    _ensureTrace();
    final ev = <String, dynamic>{
      'kind': k,
      'source': 'mobile',
      'severity': severity,
      'trace_id': _traceId,
      'session_id': _sessionId,
      'app_version': kAppVersionLabel,
      if (stage.isNotEmpty) 'stage': stage,
      if (message.isNotEmpty)
        'message': message.length > 200 ? message.substring(0, 200) : message,
      if (route.isNotEmpty) 'route': route,
      if (jobId.isNotEmpty) 'job_id': jobId,
      if (cacheId.isNotEmpty) 'cache_id': cacheId,
      if (percent != null) 'percent': percent.clamp(0, 100),
      if (httpStatus != null) 'http_status': httpStatus,
      if (ok != null) 'ok': ok,
      if (code.isNotEmpty) 'code': code,
      if (details.isNotEmpty) 'details': _safeDetails(details),
    };
    _ring.add(ev);
    while (_ring.length > maxRing) {
      _ring.removeAt(0);
    }
    if (_ring.length >= maxBatch) {
      unawaited(flush());
    }
  }

  Map<String, Object?> _safeDetails(Map<String, Object?> raw) {
    final out = <String, Object?>{};
    for (final e in raw.entries) {
      final key = e.key.trim();
      if (key.isEmpty || !RegExp(r'^[a-z][a-z0-9_]{0,39}$').hasMatch(key)) {
        continue;
      }
      final v = e.value;
      if (v is bool || v is int) {
        out[key] = v;
      } else if (v is double) {
        out[key] = v;
      } else if (v is String) {
        final s = v.trim();
        if (s.isNotEmpty && RegExp(r'^[a-z][a-z0-9_]{0,63}$').hasMatch(s)) {
          out[key] = s;
        }
      }
    }
    return out;
  }

  /// POST batch; on failure keep ring (no recursive [record]).
  Future<void> flush() async {
    if (!_enabled || _flushing || _client == null || _ring.isEmpty) return;
    _flushing = true;
    try {
      final batch = List<Map<String, dynamic>>.from(
        _ring.take(maxBatch),
      );
      try {
        await _client!.postEvidenceBatch(batch);
        _ring.removeRange(0, batch.length);
      } catch (_) {
        // KEEP ring for next flush; never emit client_api_fail for evidence POST.
      }
    } finally {
      _flushing = false;
    }
  }

  /// Test helper: clear ring without network.
  void clearForTest() {
    _ring.clear();
  }

  /// Test helper: pending count.
  int get pendingCount => _ring.length;

  void dispose() {
    _timer?.cancel();
    _timer = null;
  }
}
