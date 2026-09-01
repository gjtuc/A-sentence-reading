import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sentence_reading/api/auth_deeplink.dart';
import 'package:sentence_reading/api/client.dart';
import 'package:sentence_reading/api/session_store.dart';
import 'package:sentence_reading/state/auth_controller.dart';

class _SilentDeepLinks extends AuthDeepLinkBridge {
  @override
  Future<void> start() async {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('bootstrap network fail with cookie → sessionRestorePending', () async {
    final sessions = MemorySessionStore();
    await sessions.writeToken('cookie_value_here');
    final client = AsrClient(
      sessionStore: sessions,
      httpClient: MockClient((req) async {
        if (req.url.path.endsWith('/api/auth/status')) {
          throw http.ClientException('simulated hang');
        }
        return http.Response(
          '{"ok":true,"version":"0.3.123","mobile_login_required":true}',
          200,
          headers: {'content-type': 'application/json'},
        );
      }),
    );
    final auth = AuthController(client: client, deepLinks: _SilentDeepLinks());
    await auth.bootstrap();
    expect(auth.sessionRestorePending, isTrue);
    expect(auth.isLoggedIn, isFalse);
    expect(auth.error, contains('서버 연결'));
    auth.dispose();
  }, timeout: const Timeout(Duration(seconds: 60)));

  test('bootstrap 401 → logged out, not restore pending', () async {
    final sessions = MemorySessionStore();
    await sessions.writeToken('stale');
    final client = AsrClient(
      sessionStore: sessions,
      httpClient: MockClient((req) async {
        if (req.url.path.endsWith('/api/auth/status')) {
          return http.Response(
            '{"ok":false,"error":"invalid_token","message":"invalid_token"}',
            401,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('{"ok":true}', 200);
      }),
    );
    final auth = AuthController(client: client, deepLinks: _SilentDeepLinks());
    await auth.bootstrap();
    expect(auth.sessionRestorePending, isFalse);
    expect(auth.isLoggedIn, isFalse);
    auth.dispose();
  });
}
