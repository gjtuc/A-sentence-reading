import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/practice_evidence/practice_evidence_controller.dart';
import 'package:sentence_reading/practice_evidence/practice_evidence_store.dart';

void main() {
  test('practice evidence store never queues after kill', () async {
    final store = PracticeEvidenceStore();
    await store.append({
      'kind': 'practice_cycle_wide',
      'source': 'mobile',
      'ok': true,
    });
    expect(await store.pendingCount(), 0);
    expect(await store.peek(10), isEmpty);
  });

  test('controller commitProbe does not enqueue', () async {
    final store = PracticeEvidenceStore();
    final ctl = PracticeEvidenceController(store: store);
    ctl.setServerEnabled(true);
    expect(ctl.serverEnabled, isFalse);
    final probe = ctl.beginCycle(
      cacheId: 'c1',
      sentenceId: 1,
      chunkIndex: 0,
      baseRate: 1.0,
      groomScale: 1.0,
      focusElapsedMs: 0,
    );
    await ctl.commitProbe(probe, ok: true);
    expect(await store.pendingCount(), 0);
  });
}
