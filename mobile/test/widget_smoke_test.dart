import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sentence_reading/api/client.dart';
import 'package:sentence_reading/api/session_store.dart';
import 'package:sentence_reading/app.dart';
import 'package:sentence_reading/state/auth_controller.dart';

void main() {
  testWidgets('home shell shows brand and email login form', (tester) async {
    final mock = MockClient((request) async {
      if (request.url.path.endsWith('/api/auth/status')) {
        return http.Response(
          '{"ok":true,"auth_enabled":true,"providers":{"email":true,"google":false,"kakao":false},"user":null}',
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (request.url.path.endsWith('/api/status')) {
        return http.Response(
          '{"ok":true,"version":"0.2.69","pipeline":"rich-v7","mobile_flutter_scaffold":true,"mobile_android_platform":true,"mobile_email_auth":true}',
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      return http.Response('{}', 404);
    });
    final client = AsrClient(
      httpClient: mock,
      sessionStore: MemorySessionStore(),
    );
    final auth = AuthController(client: client);
    // Complete bootstrap before pumping UI so LoginScreen has no perpetual spinner.
    await auth.bootstrap();
    expect(auth.bootstrapping, isFalse);

    await tester.pumpWidget(SentenceReadingApp(auth: auth));
    await tester.pump();
    expect(find.textContaining('문장 읽기'), findsWidgets);

    await tester.tap(find.text('로그인'));
    await tester.pump();
    expect(find.textContaining('이메일 로그인'), findsOneWidget);
  });
}
