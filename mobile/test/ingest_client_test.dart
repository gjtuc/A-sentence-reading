import 'dart:typed_data';

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

  test('ingestPdfBytes polls job then returns cache id', () async {
    var polls = 0;
    final store = MemorySessionStore();
    await store.writeToken('tok');
    final client = AsrClient(
      httpClient: MockClient((request) async {
        if (request.method == 'POST' &&
            request.url.path.endsWith('/api/ingest')) {
          return http.Response(
            '{"ok":true,"job_id":"job_abc","percent":1}',
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        if (request.url.path.contains('/api/ingest/jobs/')) {
          polls += 1;
          if (polls < 2) {
            return http.Response(
              '{"ok":true,"job_id":"job_abc","percent":40,"done":false,"message":"processing"}',
              200,
              headers: {'content-type': 'application/json'},
            );
          }
          return http.Response(
            '{"ok":true,"job_id":"job_abc","percent":100,"done":true,"cache_id":"cafebabe12","session_id":"ses1","title":"T"}',
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('{}', 404);
      }),
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
      httpClient: MockClient((request) async {
        if (request.method == 'POST' &&
            request.url.path.endsWith('/api/ingest')) {
          return http.Response(
            '{"ok":true,"job_id":"job_y","percent":1}',
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response(
          '{"ok":true,"done":true,"session_id":"ses_only","percent":100,"message":"완료"}',
          200,
          headers: {'content-type': 'application/json'},
        );
      }),
      sessionStore: store,
    );

    await expectLater(
      client.ingestPdfBytes(
        filename: 'paper.pdf',
        bytes: _tinyPdf(),
        pollInterval: const Duration(milliseconds: 1),
      ),
      throwsA(isA<AsrApiException>()),
    );
  });

  test('ingestPdfBytes fail-closed when job ok false', () async {
    final store = MemorySessionStore();
    await store.writeToken('tok');
    final client = AsrClient(
      httpClient: MockClient((request) async {
        if (request.method == 'POST' &&
            request.url.path.endsWith('/api/ingest')) {
          return http.Response(
            '{"ok":true,"job_id":"job_x","percent":1}',
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response(
          '{"ok":false,"done":true,"error":"ingest_failed","message":"boom"}',
          200,
          headers: {'content-type': 'application/json'},
        );
      }),
      sessionStore: store,
    );

    await expectLater(
      client.ingestPdfBytes(
        filename: 'paper.pdf',
        bytes: _tinyPdf(),
        pollInterval: const Duration(milliseconds: 1),
      ),
      throwsA(
        isA<AsrApiException>().having((e) => e.message, 'msg', contains('boom')),
      ),
    );
  });
}
