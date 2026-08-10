import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/upload_draft_models.dart';
import 'package:sentence_reading/api/upload_draft_store.dart';

void main() {
  test('UploadDraft refuses bad hash / job id / upload id', () {
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
    expect(
      UploadDraft.fromJson({
        'content_hash': 'a' * 64,
        'filename': 'a.pdf',
        'upload_id': 'upl_bad!!!!!',
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
    expect(d.canResumeChunks, isFalse);
    final parsed = UploadDraft.tryParse(d.encode());
    expect(parsed, isNotNull);
    expect(parsed!.jobId, d.jobId);

    final chunking = UploadDraft(
      contentHash: 'cd' * 32,
      filename: 'chunk.pdf',
      uploadId: 'upl_abcd1234ef01',
      phase: 'uploading',
      bytesLen: 300000,
    );
    expect(chunking.canResumeChunks, isTrue);
    expect(chunking.canReattach, isFalse);
    expect(UploadDraft.tryParse(chunking.encode())!.uploadId, chunking.uploadId);

    final store = MemoryUploadDraftStore();
    await store.write(d);
    expect((await store.read())?.filename, 'paper.pdf');
    await store.clear();
    expect(await store.read(), isNull);
  });
}
