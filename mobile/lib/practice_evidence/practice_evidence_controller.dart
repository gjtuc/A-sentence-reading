/// design/209 — KILLED 0.3.211: no collection, no flush, no cloud capacity.
library;

import '../api/client.dart';
import 'practice_cycle_probe.dart';
import 'practice_evidence_store.dart';

class PracticeEvidenceController {
  PracticeEvidenceController({
    PracticeEvidenceStore? store,
  }) : _store = store ?? PracticeEvidenceStore();

  final PracticeEvidenceStore _store;

  bool serverEnabled = false;
  AsrClient? _client;

  void attachClient(AsrClient client) {
    _client = client;
  }

  void setServerEnabled(bool on) {
    // Ignored — feature hard-killed.
    serverEnabled = false;
    // ignored — hard-killed
  }

  Future<void> bindUid(String? uid) async {
    await _store.bindUid(uid);
    await _store.clearAll();
  }

  void resetSessionSeq() {}

  PracticeCycleProbe beginCycle({
    required String cacheId,
    required int sentenceId,
    required int chunkIndex,
    required double baseRate,
    required double groomScale,
    required int focusElapsedMs,
  }) {
    // Dead probe — never committed.
    return PracticeCycleProbe(
      cacheId: cacheId,
      sentenceId: sentenceId,
      chunkIndex: chunkIndex,
      cycleSeq: 0,
      baseRate: baseRate,
      groomScale: groomScale,
      focusElapsedMs: focusElapsedMs,
    );
  }

  Future<void> commitProbe(PracticeCycleProbe probe, {required bool ok}) async {
    // no-op
    // No local append.
  }

  Future<void> flush({String cacheId = ''}) async {
    // no-op
    // no-op
    await _store.clearAll();
  }
}
