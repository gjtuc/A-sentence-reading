/// design/209 — KILLED 0.3.211: never upload practice cycle evidence.
library;

import '../api/client.dart';
import 'practice_evidence_store.dart';

class PracticeEvidenceUploader {
  PracticeEvidenceUploader({
    required this.store,
    this.batchSize = 50,
  });

  final PracticeEvidenceStore store;
  final int batchSize;

  Future<void> flush({
    required AsrClient client,
    required bool serverEnabled,
    String cacheId = '',
  }) async {
    // no-op killed; params unused
    await store.clearAll();
  }
}

/// Process-wide helpers (kept for tests; unused by practice screen after kill).
final practiceEvidenceStore = PracticeEvidenceStore();
final practiceEvidenceUploader =
    PracticeEvidenceUploader(store: practiceEvidenceStore);
