import 'dart:convert';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sentence_reading/api/client.dart';
import 'package:sentence_reading/api/session_store.dart';

Uint8List _tinyPdf() {
  // Minimal %PDF header bytes — server would still reject as invalid PDF body,
  // but client magic check only needs the header for preflight.
  return Uint8List.fromList('%PDF-1.4\n%\xe2\xe3\xcf\xd3\n'.codeUnits);
}

String _sha(List<int> b) => sha256.convert(b).toString();

/// Mock that speaks design/72 chunked create/put/complete + job poll.
MockClient _chunkedThenPoll({
  required String jobId,
  required http.Response Function(int polls) onPoll,
}) {
  var polls = 0;
  var offset = 0;
  final bytes = _tinyPdf();
  final digest = _sha(bytes);
  const upl = 'upl_abcd1234ef01';
  return MockClient((request) async {
    final path = request.url.path;
    if (request.method == 'POST' && path.endsWith('/api/ingest/uploads')) {
      return http.Response(
        jsonEncode({
          'ok': true,
          'upload_id': upl,
          'content_hash': digest,
          'size': bytes.length,
          'chunk_size': 262144,
          'received_offset': 0,
          'prefix_sha256': '',
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (request.method == 'PUT' && path.contains('/api/ingest/uploads/')) {
      final body = request.bodyBytes;
      offset += body.length;
      return http.Response(
        jsonEncode({
          'ok': true,
          'upload_id': upl,
          'received_offset': offset,
          'prefix_sha256': _sha(bytes.sublist(0, offset)),
          'chunk_size': 262144,
          'size': bytes.length,
          'content_hash': digest,
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (request.method == 'POST' && path.endsWith('/complete')) {
      return http.Response(
        jsonEncode({
          'ok': true,
          'job_id': jobId,
          'percent': 1,
          'content_hash': digest,
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (path.contains('/api/ingest/jobs/')) {
      polls += 1;
      return onPoll(polls);
    }
    return http.Response('{}', 404);
  });
}

/// Kill-switch path: chunked create 503 → multipart /api/ingest.
MockClient _multipartFallbackThen({
  required http.Response Function(http.Request request) afterIngest,
}) {
  return MockClient((request) async {
    if (request.method == 'POST' &&
        request.url.path.endsWith('/api/ingest/uploads')) {
      return http.Response(
        '{"ok":false,"error":"chunked_upload_disabled","message":"off"}',
        503,
        headers: {'content-type': 'application/json'},
      );
    }
    if (request.method == 'POST' &&
        request.url.path.endsWith('/api/ingest')) {
      return http.Response(
        '{"ok":true,"job_id":"job_abcd1234ef99","percent":1}',
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    return afterIngest(request);
  });
}

void main() {
  test('ingestPdfBytes refuses empty / non-pdf / no session', () async {
    final store = MemorySessionStore();
    final client = AsrClient(
      httpClient: MockClient((_) async => http.Response('{}', 404)),
      sessionStore: store,
    );

    await expectLater(
      client.ingestPdfBytes(filename: 'a.pdf', bytes: Uint8List(0)),
      throwsA(isA<AsrApiException>()),
    );
    await expectLater(
      client.ingestPdfBytes(
        filename: 'a.docx',
        bytes: _tinyPdf(),
      ),
      throwsA(isA<AsrApiException>()),
    );
    await expectLater(
      client.ingestPdfBytes(filename: 'a.pdf', bytes: _tinyPdf()),
      throwsA(
        isA<AsrApiException>().having((e) => e.statusCode, 'status', 401),
      ),
    );
  });

  test('ingestPdfBytes chunked put → poll → cache id', () async {
    final store = MemorySessionStore();
    await store.writeToken('tok');
    final client = AsrClient(
      httpClient: _chunkedThenPoll(
        jobId: 'job_abcd1234ef01',
        onPoll: (polls) {
          if (polls < 2) {
            return http.Response(
              '{"ok":true,"job_id":"job_abcd1234ef01","percent":40,"done":false,"message":"processing"}',
              200,
              headers: {'content-type': 'application/json'},
            );
          }
          return http.Response(
            '{"ok":true,"job_id":"job_abcd1234ef01","percent":100,"done":true,"cache_id":"cafebabe12","session_id":"ses1","title":"T"}',
            200,
            headers: {'content-type': 'application/json'},
          );
        },
      ),
      sessionStore: store,
    );

    final progress = <int>[];
    final result = await client.ingestPdfBytes(
      filename: 'paper.pdf',
      bytes: _tinyPdf(),
      pollInterval: const Duration(milliseconds: 1),
      onProgress: (p, _) => progress.add(p),
    );
    expect(result.cacheId, 'cafebabe12');
    expect(result.sessionId, 'ses1');
    expect(progress, isNotEmpty);
  });

  test('ingestPdfBytes fail-closed when done without cache_id', () async {
    final store = MemorySessionStore();
    await store.writeToken('tok');
    final client = AsrClient(
      httpClient: _multipartFallbackThen(
        afterIngest: (_) => http.Response(
          '{"ok":true,"done":true,"session_id":"ses_only","percent":100,"message":"완료"}',
          200,
          headers: {'content-type': 'application/json'},
        ),
      ),
      sessionStore: store,
    );

    await expectLater(
      client.ingestPdfBytes(
        filename: 'paper.pdf',
        bytes: _tinyPdf(),
        pollInterval: const Duration(milliseconds: 1),
      ),
      throwsA(
        isA<AsrApiException>()
            .having((e) => e.statusCode, 'status', 422)
            .having(
              (e) => e.message,
              'msg',
              contains('제목이 너무 짧은'),
            ),
      ),
    );
  });

  test('createChunkedUpload surfaces 429 rate limit copy', () async {
    final store = MemorySessionStore();
    await store.writeToken('tok');
    final client = AsrClient(
      httpClient: MockClient((request) async {
        if (request.method == 'POST' &&
            request.url.path.endsWith('/api/ingest/uploads')) {
          return http.Response(
            '{"ok":false,"error":"rate_limited","message":"요청이 너무 많습니다."}',
            429,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('{}', 404);
      }),
      sessionStore: store,
    );
    await expectLater(
      client.createChunkedUpload(
        filename: 'a.pdf',
        contentHash: 'ab' * 32,
        size: 12,
      ),
      throwsA(
        isA<AsrApiException>()
            .having((e) => e.statusCode, 'status', 429)
            .having((e) => e.message, 'msg', contains('요청이 너무 많습니다')),
      ),
    );
  });

  test('pollIngestJob idle timeout when percent/message stall', () async {
    final store = MemorySessionStore();
    await store.writeToken('tok');
    final client = AsrClient(
      httpClient: MockClient((request) async {
        if (request.url.path.contains('/api/ingest/jobs/')) {
          return http.Response(
            '{"ok":true,"job_id":"job_abcd1234ef01","percent":10,"done":false,"message":"stuck"}',
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('{}', 404);
      }),
      sessionStore: store,
    );

    await expectLater(
      client.pollIngestJob(
        jobId: 'job_abcd1234ef01',
        pollInterval: const Duration(milliseconds: 5),
        idleTimeout: const Duration(milliseconds: 40),
        maxDuration: const Duration(seconds: 5),
      ),
      throwsA(
        isA<AsrApiException>()
            .having((e) => e.statusCode, 'status', 504)
            .having(
              (e) => e.message,
              'msg',
              contains('이어서 분석하기'),
            ),
      ),
    );
  });

  test('pollIngestJob idle clock resets on progress change', () async {
    final store = MemorySessionStore();
    await store.writeToken('tok');
    var polls = 0;
    final client = AsrClient(
      httpClient: MockClient((request) async {
        if (request.url.path.contains('/api/ingest/jobs/')) {
          polls += 1;
          if (polls < 4) {
            return http.Response(
              '{"ok":true,"job_id":"job_abcd1234ef01","percent":10,"done":false,"message":"a"}',
              200,
              headers: {'content-type': 'application/json'},
            );
          }
          if (polls < 8) {
            return http.Response(
              '{"ok":true,"job_id":"job_abcd1234ef01","percent":20,"done":false,"message":"b"}',
              200,
              headers: {'content-type': 'application/json'},
            );
          }
          return http.Response(
            '{"ok":true,"job_id":"job_abcd1234ef01","percent":100,"done":true,"cache_id":"cafebabe12","session_id":"ses1"}',
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('{}', 404);
      }),
      sessionStore: store,
    );

    final result = await client.pollIngestJob(
      jobId: 'job_abcd1234ef01',
      pollInterval: const Duration(milliseconds: 5),
      idleTimeout: const Duration(milliseconds: 30),
      maxDuration: const Duration(seconds: 5),
    );
    expect(result.cacheId, 'cafebabe12');
  });

  test('ingestPdfBytes fail-closed when job ok false', () async {
    final store = MemorySessionStore();
    await store.writeToken('tok');
    final client = AsrClient(
      httpClient: _multipartFallbackThen(
        afterIngest: (_) => http.Response(
          '{"ok":false,"done":true,"error":"ingest_failed","message":"boom"}',
          200,
          headers: {'content-type': 'application/json'},
        ),
      ),
      sessionStore: store,
    );

    await expectLater(
      client.ingestPdfBytes(
        filename: 'paper.pdf',
        bytes: _tinyPdf(),
        pollInterval: const Duration(milliseconds: 1),
      ),
      throwsA(
        isA<AsrApiException>()
            .having((e) => e.statusCode, 'status', 422)
            .having((e) => e.message, 'msg', contains('boom')),
      ),
    );
  });
}
