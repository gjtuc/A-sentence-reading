import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/pdf_advisory_cache_store.dart';

void main() {
  test('design/309 put does not keep a title for the next lookup', () async {
    TestWidgetsFlutterBinding.ensureInitialized();
    final store = PdfAdvisoryCacheStore();
    await store.bindUid('title-not-stored');
    await store.put(
      docUri: 'content://papers/a.pdf',
      sizeBytes: 12,
      lastModifiedMs: 34,
      advisoryTitle: 'must not stick',
      advisoryRole: 'main',
      advisoryReason: 'head',
      extractOk: true,
    );
    final again = await store.lookup(
      docUri: 'content://papers/a.pdf',
      sizeBytes: 12,
      lastModifiedMs: 34,
    );
    expect(again, isNull);
    expect(kPdfAdvisoryCacheSchema, 0);
  });
}
