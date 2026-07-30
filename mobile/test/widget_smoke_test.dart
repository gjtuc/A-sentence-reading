import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sentence_reading/api/client.dart';
import 'package:sentence_reading/api/session_store.dart';
import 'package:sentence_reading/app.dart';
import 'package:sentence_reading/state/auth_controller.dart';
import 'package:sentence_reading/state/library_controller.dart';

void main() {
  testWidgets('library prompts login then lists papers when authenticated',
      (tester) async {
    var loggedIn = false;
    final mock = MockClient((request) async {
      final path = request.url.path;
      if (path.endsWith('/api/auth/status')) {
        if (loggedIn) {
          return http.Response(
            '{"ok":true,"auth_enabled":true,"providers":{"email":true},"user":{"uid":"u1","email":"a@b.c","providers":["email"]}}',
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response(
          '{"ok":true,"auth_enabled":true,"providers":{"email":true},"user":null}',
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (path.endsWith('/api/cache/papers')) {
        return http.Response(
          '{"ok":true,"papers":[{"id":"c1","title":"Sample Paper","source":"pdf","sentence_count":10,"figure_count":1,"updated_at":"2026-07-01"}]}',
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (path.endsWith('/api/status')) {
        return http.Response(
          '{"ok":true,"version":"0.2.70","pipeline":"rich-v7","mobile_library":true}',
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      return http.Response('{}', 404);
    });
    final store = MemorySessionStore();
    final client = AsrClient(httpClient: mock, sessionStore: store);
    final auth = AuthController(client: client);
    final library = LibraryController(client: client);
    await auth.bootstrap();

    await tester.pumpWidget(SentenceReadingApp(auth: auth, library: library));
    await tester.pump();
    await tester.tap(find.text('보관'));
    await tester.pump();
    expect(find.textContaining('먼저 로그인'), findsOneWidget);

    // Simulate login by writing session + re-bootstrap with user.
    loggedIn = true;
    await store.writeToken('tok');
    await auth.bootstrap();
    await tester.pump();
    await library.refresh();
    await tester.pump();
    expect(find.text('Sample Paper'), findsOneWidget);
  });
}
