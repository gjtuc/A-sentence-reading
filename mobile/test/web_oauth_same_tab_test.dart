import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sentence_reading/api/auth_deeplink.dart';
import 'package:sentence_reading/api/client.dart';
import 'package:sentence_reading/api/oauth_bridges.dart';
import 'package:sentence_reading/api/session_store.dart';
import 'package:sentence_reading/state/auth_controller.dart';

class _SilentDeepLinks extends AuthDeepLinkBridge {
  @override
  Future<void> start() async {}
}

class _NoNativeGoogle implements GoogleIdTokenSource {
  @override
  Future<String?> obtainIdToken({required String serverClientId}) async =>
      throw StateError('native Google must not run on the web');
}

class _NoCustomTab implements KakaoOAuthBrowser {
  @override
  Future<String> authenticate({
    required String startUrl,
    required String callbackUrlScheme,
  }) async =>
      throw StateError('Custom Tab must not run on the web');
}

AsrClient _client() => AsrClient(
      sessionStore: MemorySessionStore(),
      httpClient: MockClient((req) async => http.Response(
            '{"ok":true,"auth_enabled":true,"client_id":"cid.apps",'
            '"providers":{"google":true,"kakao":true,"email":true},"user":null}',
            200,
            headers: {'content-type': 'application/json'},
          )),
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  tearDown(() => AuthController.debugForceWebLogin = false);

  test('design/407 web Google and Kakao leave in the same tab and land on /app/', () async {
    AuthController.debugForceWebLogin = true;
    final opened = <Uri>[];
    final auth = AuthController(
      client: _client(),
      googleTokens: _NoNativeGoogle(),
      kakaoBrowser: _NoCustomTab(),
      deepLinks: _SilentDeepLinks(),
      openSameTab: (uri) async => opened.add(uri),
    );
    await auth.loginGoogle();
    await auth.loginKakao();
    expect(opened.map((u) => u.path), [
      '/api/auth/google/mobile/start',
      '/api/auth/kakao/start',
    ]);
    for (final u in opened) {
      expect(u.queryParameters['land'], 'app');
      expect(u.queryParameters.containsKey('mobile'), isFalse);
    }
    auth.dispose();
  });

  test('design/407 phone keeps the Custom Tab start URLs', () {
    final c = _client();
    expect(Uri.parse(c.kakaoStartUrl()).queryParameters['mobile'], '1');
    expect(Uri.parse(c.googleMobileStartUrl()).queryParameters.containsKey('land'), isFalse);
  });
}
