/// design/213 — encode + emit dense practice skill evidence (P5-safe).
library;

import 'dart:convert';

import 'package:crypto/crypto.dart';

import '../api/client.dart';
import '../config.dart';
import '../services/evidence_bus.dart';
import 'skill_evidence_store.dart';

const int kSkillEvidenceSchemaV = 1;

String skillSentenceIdH16(String sentenceId) {
  final d = sha256.convert(utf8.encode(sentenceId.trim()));
  // details strings must match ^[a-z][a-z0-9_]{0,63}$
  return 'h${d.toString().substring(0, 15)}';
}

String accuracyBin(double accuracy) {
  final p = (accuracy * 100).floor();
  if (p < 40) return 'bin_0_39';
  if (p < 60) return 'bin_40_59';
  if (p < 75) return 'bin_60_74';
  if (p < 90) return 'bin_75_89';
  return 'bin_90_100';
}

Map<String, Object?> skillSafeDetails(Map<String, Object?> raw) {
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
      out[key] = double.parse(v.toStringAsFixed(3));
    } else if (v is String) {
      final s = v.trim();
      if (s.isNotEmpty && RegExp(r'^[a-z][a-z0-9_]{0,63}$').hasMatch(s)) {
        out[key] = s;
      }
    }
  }
  out['schema_v'] = kSkillEvidenceSchemaV;
  return out;
}

class SkillEvidenceEmitter {
  SkillEvidenceEmitter({SkillEvidenceStore? store})
      : store = store ?? SkillEvidenceStore();

  final SkillEvidenceStore store;
  bool enabled = true;
  AsrClient? _client;
  String _traceId = '';
  String _sessionId = '';
  int _seq = 0;

  void attachClient(AsrClient client) => _client = client;

  void setEnabled(bool on) => enabled = on;

  Future<void> bindUid(String? uid) => store.bindUid(uid);

  void resetSessionSeq() => _seq = 0;

  void _ensureIds() {
    if (_traceId.isNotEmpty) return;
    final bus = asrEvidenceBus;
    if (bus != null && bus.traceId.isNotEmpty) {
      _traceId = bus.traceId;
    } else {
      _traceId =
          'tr_${DateTime.now().millisecondsSinceEpoch.toRadixString(16)}';
    }
    _sessionId =
        'ses_${DateTime.now().millisecondsSinceEpoch.toRadixString(16)}';
  }

  Future<void> emit({
    required String kind,
    required String cacheId,
    bool ok = true,
    String code = '',
    Map<String, Object?> details = const {},
  }) async {
    if (!enabled) return;
    _ensureIds();
    _seq += 1;
    final det = skillSafeDetails({
      ...details,
      'seq': _seq,
    });
    final ev = <String, dynamic>{
      'kind': kind,
      'source': 'mobile',
      'severity': 'boundary',
      'trace_id': _traceId,
      'session_id': _sessionId,
      'app_version': kAppVersionLabel,
      'ok': ok,
      if (code.isNotEmpty) 'code': code,
      if (cacheId.isNotEmpty) 'cache_id': cacheId,
      'details': det,
    };
    await store.append(ev);
    asrEvidenceBus?.record(
      kind,
      cacheId: cacheId,
      ok: ok,
      code: code,
      details: det,
    );
  }

  Future<void> flush({String cacheId = ''}) async {
    if (!enabled) {
      await store.clearAll();
      return;
    }
    final c = _client;
    if (c == null) return;
    var pending = await store.pendingCount();
    var acceptedTotal = 0;
    var droppedTotal = 0;
    while (pending > 0) {
      final batch = await store.peek(50);
      if (batch.isEmpty) break;
      try {
        final r = await c.postEvidenceBatch(batch);
        await store.ack(batch.length);
        acceptedTotal += r.accepted;
        droppedTotal += r.dropped;
      } catch (_) {
        break;
      }
      pending = await store.pendingCount();
    }
    await emit(
      kind: 'practice_skill_flush',
      cacheId: cacheId,
      ok: true,
      details: {
        'phase': 'flush',
        'accepted': acceptedTotal,
        'dropped': droppedTotal,
        'pending_n': await store.pendingCount(),
      },
    );
    // Flush the flush meta itself once.
    final tail = await store.peek(10);
    if (tail.isNotEmpty && c != null) {
      try {
        await c.postEvidenceBatch(tail);
        await store.ack(tail.length);
      } catch (_) {}
    }
  }
}
