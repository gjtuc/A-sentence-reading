// design/453 — a hidden paper is deleted for good 20 seconds later.
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/library_soft_delete_models.dart';
import 'package:sentence_reading/api/library_soft_delete_store.dart';

void main() {
  test('the wait before deleting for good is 20 seconds', () async {
    expect(kSoftDeleteGrace, const Duration(seconds: 20));
    final store = MemoryLibrarySoftDeleteStore();
    await store.bindUid('u');
    final list = await store.hide(['p1'], nowMs: 1000000);
    expect(list.entries.single.purgeAtMs, 1000000 + 20000);
    expect(list.dueAt(1000000 + 19999), isEmpty);
    expect(list.dueAt(1000000 + 20000).map((e) => e.cacheId), ['p1']);
  });
}
