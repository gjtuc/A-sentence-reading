import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sentence_reading/api/client.dart';
import 'package:sentence_reading/api/session_store.dart';
import 'package:sentence_reading/app.dart';
import 'package:sentence_reading/state/auth_controller.dart';
import 'package:sentence_reading/state/library_controller.dart';

void main() {
  testWidgets('login gate then library lists papers when authenticated',
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
          '{"ok":true,"version":"0.2.87","pipeline":"rich-v7","mobile_library":true,"mobile_shell_nav":true,"mobile_upload":true}',
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      // WHY: SettingsScreen (IndexedStack) may call access APIs after login.
      // EDGE: missing mock → 404 noise / incomplete settle; not a success path.
      if (path.endsWith('/api/access/status')) {
        return http.Response(
          '{"ok":true,"gate_enabled":true,"invite_pool_ready":false,"status":"none","effective":"none","can_use_paid":false,"is_admin":false,"invited_at":null,"decided_at":null,"decision_note":"","code_format":"XXXX-XXXX"}',
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (path.contains('/api/access/admin/')) {
        return http.Response(
          '{"ok":false,"error":"admin_required","message":"admin only"}',
          403,
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

    // WHY (design/68): logged-out shell is login-only — no bottom nav / 보관 tab.
    // EDGE: old smoke tapped 보관 while logged out; that destination is gone.
    // EDGE: title 「로그인」 and submit button both say 로그인 — use email-mode label.
    expect(find.text('보관'), findsNothing);
    expect(find.text('이메일 로그인'), findsOneWidget);
    expect(find.text('로그인'), findsWidgets);

    // Simulate login by writing session + re-bootstrap with user.
    loggedIn = true;
    await store.writeToken('tok');
    await auth.bootstrap();
    await tester.pump();
    await library.refresh();
    await tester.pump();

    expect(find.text('보관'), findsOneWidget);
    expect(find.text('Sample Paper'), findsOneWidget);
  });
}
