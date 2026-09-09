/// design/209 — session facade: probe → durable store; flush after focus.
library;

import 'dart:math';

import '../api/client.dart';
import '../config.dart';
import '../services/evidence_bus.dart';
import 'practice_cycle_probe.dart';
import 'practice_evidence_encode.dart';
import 'practice_evidence_store.dart';
import 'practice_evidence_uploader.dart';

class PracticeEvidenceController {
  PracticeEvidenceController({
    PracticeEvidenceStore? store,
    PracticeEvidenceUploader? uploader,
  })  : _store = store ?? practiceEvidenceStore,
        _uploader = uploader ??
            PracticeEvidenceUploader(store: store ?? practiceEvidenceStore);

  final PracticeEvidenceStore _store;
  final PracticeEvidenceUploader _uploader;

  bool serverEnabled = true;
  int _cycleSeq = 0;
  AsrClient? _client;

  void attachClient(AsrClient client) {
    _client = client;
  }

  void setServerEnabled(bool on) {
    serverEnabled = on;
  }

  Future<void> bindUid(String? uid) => _store.bindUid(uid);

  void resetSessionSeq() {
    _cycleSeq = 0;
  }

  PracticeCycleProbe beginCycle({
    required String cacheId,
    required int sentenceId,
    required int chunkIndex,
    required double baseRate,
    required double groomScale,
    required int focusElapsedMs,
  }) {
    _cycleSeq += 1;
    return PracticeCycleProbe(
      cacheId: cacheId,
      sentenceId: sentenceId,
      chunkIndex: chunkIndex,
      cycleSeq: _cycleSeq,
      baseRate: baseRate,
      groomScale: groomScale,
      focusElapsedMs: focusElapsedMs,
    );
  }

  Future<void> commitProbe(PracticeCycleProbe probe, {required bool ok}) async {
    if (!serverEnabled) return;
    probe.markComplete();
    final bus = asrEvidenceBus;
    var trace = bus?.traceId ?? '';
    if (trace.isEmpty) trace = _newId('tr_', 16);
    // kind practice_cycle_wide — design/209 floor marker
    final ev = buildPracticeCycleEvent(
      details: probe.toDetails(),
      cacheId: probe.cacheId,
      appVersion: kAppVersionLabel,
      traceId: trace,
      sessionId: _newId('ses_', 12),
      code: probe.outcome,
      ok: ok && probe.ttsOk == 1,
    );
    try {
      await _store.append(ev);
    } catch (_) {
      // Never break practice loop.
    }
  }

  Future<void> flush({String cacheId = ''}) async {
    final c = _client;
    if (c == null || !serverEnabled) return;
    await _uploader.flush(
      client: c,
      serverEnabled: serverEnabled,
      cacheId: cacheId,
    );
  }

  static String _newId(String prefix, int hexLen) {
    final r = Random.secure();
    final buf = StringBuffer(prefix);
    for (var i = 0; i < hexLen; i++) {
      buf.write(r.nextInt(16).toRadixString(16));
    }
    return buf.toString();
  }
}
