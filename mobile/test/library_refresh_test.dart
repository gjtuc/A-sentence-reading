import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sentence_reading/api/client.dart';
import 'package:sentence_reading/api/session_store.dart';
import 'package:sentence_reading/api/upload_draft_store.dart';
import 'package:sentence_reading/state/library_controller.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('refresh keeps papers on TimeoutException', () async {
    final store = MemorySessionStore();
    await store.writeToken('tok');
    var calls = 0;
    final client = AsrClient(
      sessionStore: store,
      httpClient: MockClient((request) async {
        if (request.url.path.endsWith('/api/cache/papers')) {
          calls += 1;
          if (calls == 1) {
            return http.Response(
              '{"ok":true,"papers":[{"id":"abcd1234","title":"Paper A"}]}',
              200,
              headers: {'content-type': 'application/json'},
            );
          }
          throw TimeoutException('slow');
        }
        if (request.url.path.endsWith('/api/auth/status')) {
          return http.Response(
            '{"ok":true,"user":{"uid":"u1","email":"a@b.c"}}',
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('{}', 404);
      }),
    );

    final library = LibraryController(
      client: client,
      draftStore: MemoryUploadDraftStore(),
    );
    await library.refresh();
    expect(library.papers.length, 1);
    expect(library.papers.first.id, 'abcd1234');

    await library.refresh();
    expect(library.papers.length, 1);
    expect(library.error, contains('서버 응답이 느립니다'));
  });
}
