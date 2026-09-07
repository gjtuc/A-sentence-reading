import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sentence_reading/api/client.dart';
import 'package:sentence_reading/api/paper_models.dart';
import 'package:sentence_reading/api/session_store.dart';
import 'package:sentence_reading/api/upload_draft_store.dart';
import 'package:sentence_reading/state/library_controller.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('deletePapers keeps row on TimeoutException (design/177)', () async {
    final store = MemorySessionStore();
    await store.writeToken('tok');
    final client = AsrClient(
      sessionStore: store,
      httpClient: MockClient((request) async {
        if (request.method == 'DELETE' &&
            request.url.path.contains('/api/cache/papers/')) {
          expect(request.headers['X-Asr-Handoff-Id'], startsWith('hf_'));
          throw TimeoutException('Future not completed');
        }
        return http.Response('{}', 404);
      }),
    );
    final lib = LibraryController(
      client: client,
      draftStore: MemoryUploadDraftStore(),
    );
    lib.papers = [
      PaperEntry.fromJson({
        'id': 'abcd1234abcd',
        'title': 'Paper A',
        'source': 'pdf',
      }),
    ];
    expect(lib.papers.length, 1);

    final n = await lib.deletePapers(['abcd1234abcd']);
    expect(n, 0);
    expect(lib.papers.length, 1);
    expect(lib.error, contains('시간 초과'));
    expect(lib.error, isNot(contains('TimeoutException')));
  });
}
