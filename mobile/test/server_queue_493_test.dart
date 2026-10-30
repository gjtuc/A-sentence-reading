// design/493 — the server holds the upload line; the app sends files ahead.
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sentence_reading/api/client.dart';
import 'package:sentence_reading/api/session_store.dart';
import 'package:sentence_reading/api/upload_reserve_models.dart';

Uint8List _tinyPdf() =>
    Uint8List.fromList('%PDF-1.4\n%\xe2\xe3\xcf\xd3\n'.codeUnits);

String _sha(List<int> b) => sha256.convert(b).toString();

http.Response _json(Object body) => http.Response(
      jsonEncode(body),
      200,
      headers: {'content-type': 'application/json'},
    );

void main() {
  test('reserve item keeps its server job id', () {
    final item = UploadReserveItem(
      contentHash: 'a' * 64,
      filename: 'a.pdf',
      jobId: 'job_abcd1234ef01',
    );
    expect(item.isSent, isTrue);
    final back = UploadReserveItem.fromJson(item.toJson())!;
    expect(back.jobId, 'job_abcd1234ef01');
    expect(back.copyWith(status: 'active').jobId, 'job_abcd1234ef01');

    final bad = UploadReserveItem.fromJson({
      'content_hash': 'b' * 64,
      'filename': 'b.pdf',
      'job_id': '../x',
    })!;
    expect(bad.isSent, isFalse);
    expect(
      UploadReserveItem(contentHash: 'c' * 64, filename: 'c.pdf')
          .toJson()
          .containsKey('job_id'),
      isFalse,
    );
  });

  test('chunked start asks for the queue and reads queued', () async {
    final store = MemorySessionStore();
    await store.writeToken('tok');
    final bytes = _tinyPdf();
    final digest = _sha(bytes);
    const upl = 'upl_abcd1234ef01';
    var offset = 0;
    Uri? completeUrl;
    final client = AsrClient(
      httpClient: MockClient((request) async {
        final path = request.url.path;
        if (request.method == 'POST' && path.endsWith('/api/ingest/uploads')) {
          return _json({
            'ok': true,
            'upload_id': upl,
            'content_hash': digest,
            'size': bytes.length,
            'chunk_size': 262144,
            'received_offset': 0,
            'prefix_sha256': '',
          });
        }
        if (request.method == 'PUT') {
          offset += request.bodyBytes.length;
          return _json({
            'ok': true,
            'upload_id': upl,
            'received_offset': offset,
            'prefix_sha256': _sha(bytes.sublist(0, offset)),
            'chunk_size': 262144,
            'size': bytes.length,
            'content_hash': digest,
          });
        }
        if (path.endsWith('/complete')) {
          completeUrl = request.url;
          return _json({
            'ok': true,
            'job_id': 'job_abcd1234ef02',
            'content_hash': digest,
            'queued': true,
            'queue_position': 1,
          });
        }
        return http.Response('{}', 404);
      }),
      sessionStore: store,
    );
    final started = await client.startIngestPdfBytesChunked(
      filename: 'a.pdf',
      bytes: bytes,
      contentHash: digest,
      queue: true,
      adoptTrace: false,
    );
    expect(started.jobId, 'job_abcd1234ef02');
    expect(started.queued, isTrue);
    expect(completeUrl!.queryParameters['queue'], '1');
  });

  test('a waiting job outlives the idle timeout and reports jobs ahead',
      () async {
    final store = MemorySessionStore();
    await store.writeToken('tok');
    var polls = 0;
    final client = AsrClient(
      httpClient: MockClient((request) async {
        polls += 1;
        if (polls < 12) {
          return _json({
            'ok': true,
            'job_id': 'job_abcd1234ef01',
            'percent': 1,
            'stage': 'waiting',
            'done': false,
            'message': 'wait',
            'queue_waiting': true,
            'queue_ahead': 2,
          });
        }
        return _json({
          'ok': true,
          'job_id': 'job_abcd1234ef01',
          'percent': 100,
          'done': true,
          'cache_id': 'cafebabe12',
          'session_id': 'ses1',
        });
      }),
      sessionStore: store,
    );
    final ahead = <int?>[];
    final result = await client.pollIngestJob(
      jobId: 'job_abcd1234ef01',
      pollInterval: const Duration(milliseconds: 5),
      idleTimeout: const Duration(milliseconds: 30),
      maxDuration: const Duration(seconds: 5),
      onWaiting: ahead.add,
    );
    expect(result.cacheId, 'cafebabe12');
    expect(ahead, isNotEmpty);
    expect(ahead.first, 2);
  });

  test('controller sends the line ahead and reattaches sent files', () {
    final src = File('lib/state/library_controller.dart').readAsStringSync();
    expect(src, contains('Future<void> _sendAheadQueue()'));
    expect(src, contains('queue: true,'));
    expect('onWaiting: _noteQueueWaiting'.allMatches(src).length, 2);
    expect(src, contains('result = await _finishWithPoll(sentDraft);'));
    expect(src, contains("if (reason == 'user')"));
    for (final f in [
      'lib/widgets/upload_queue_sheet.dart',
      'lib/widgets/upload_picker_sheet.dart',
    ]) {
      expect(File(f).readAsStringSync(), contains("reason: 'user'"), reason: f);
    }
  });
}
