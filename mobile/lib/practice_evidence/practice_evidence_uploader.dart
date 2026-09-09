/// design/209 — post durable practice cycle events after focus ends.
library;

import '../api/client.dart';
import '../services/evidence_bus.dart';
import 'practice_evidence_store.dart';

class PracticeEvidenceUploader {
  PracticeEvidenceUploader({
    required this.store,
    this.batchSize = 50,
  });

  final PracticeEvidenceStore store;
  final int batchSize;
  bool _flushing = false;

  /// Drain local queue to `/api/evidence/ingest`. Safe to call overlapping.
  Future<void> flush({
    required AsrClient client,
    required bool serverEnabled,
    String cacheId = '',
  }) async {
    if (!serverEnabled || _flushing) return;
    _flushing = true;
    var batches = 0;
    var acceptedSum = 0;
    var droppedSum = 0;
    try {
      while (true) {
        final batch = await store.peek(batchSize);
        if (batch.isEmpty) break;
        try {
          final r = await client.postEvidenceBatch(batch);
          acceptedSum += r.accepted;
          droppedSum += r.dropped;
          await store.ack(batch.length);
          batches += 1;
        } catch (_) {
          break;
        }
      }
      if (batches > 0 || store.droppedLocal > 0) {
        asrEvidenceBus?.record(
          'practice_evidence_flush',
          cacheId: cacheId,
          ok: true,
          details: {
            'batches': batches,
            'accepted': acceptedSum,
            'dropped_server': droppedSum,
            'dropped_local': store.droppedLocal,
          },
        );
      }
    } finally {
      _flushing = false;
    }
  }
}

/// Process-wide helpers bound from practice screen.
final practiceEvidenceStore = PracticeEvidenceStore();
final practiceEvidenceUploader =
    PracticeEvidenceUploader(store: practiceEvidenceStore);
