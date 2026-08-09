import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/upload_draft_models.dart';
import 'package:sentence_reading/api/upload_draft_store.dart';

void main() {
  test('UploadDraft refuses bad hash / job id', () {
    expect(UploadDraft.tryParse(''), isNull);
    expect(
      UploadDraft.fromJson({
        'content_hash': 'abc',
        'filename': 'a.pdf',
      }),
      isNull,
    );
    expect(
      UploadDraft.fromJson({
        'content_hash': 'a' * 64,
        'filename': 'a.pdf',
        'job_id': 'job_not_hex!!!!',
      }),
      isNull,
    );
  });

  test('UploadDraft round-trip + memory store clear', () async {
    final d = UploadDraft(
      contentHash: 'ab' * 32,
      filename: 'paper.pdf',
      jobId: 'job_abcd1234ef01',
      phase: 'processing',
      localPath: 'memory/ingest_drafts/${'ab' * 32}.pdf',
      bytesLen: 12,
    );
    expect(d.canReattach, isTrue);
    final parsed = UploadDraft.tryParse(d.encode());
    expect(parsed, isNotNull);
    expect(parsed!.jobId, d.jobId);

    final store = MemoryUploadDraftStore();
    await store.write(d);
    expect((await store.read())?.filename, 'paper.pdf');
    await store.clear();
    expect(await store.read(), isNull);
  });
}
