/// App-wide auth session (email · Google · Kakao · design/61·65).
library;

import 'package:flutter/foundation.dart';

import '../api/auth_models.dart';
import '../api/client.dart';
import '../api/oauth_bridges.dart';
import '../api/oauth_models.dart';

/// Holds current [AsrUser] and drives login/register/logout/restore/OAuth.
class AuthController extends ChangeNotifier {
  AuthController({
    AsrClient? client,
    GoogleIdTokenSource? googleTokens,
    KakaoOAuthBrowser? kakaoBrowser,
  })  : _client = client ?? AsrClient(),
        _googleTokens = googleTokens ?? GoogleSignInIdTokenSource(),
        _kakaoBrowser = kakaoBrowser ?? FlutterWebAuthKakaoBrowser();

  final AsrClient _client;
  final GoogleIdTokenSource _googleTokens;
  final KakaoOAuthBrowser _kakaoBrowser;

  AsrClient get client => _client;

  AsrUser? user;
  AsrAuthStatus? lastStatus;
  bool bootstrapping = true;
  bool busy = false;
  String? error;

  bool get isLoggedIn => user != null && !user!.isEmpty;

  /// On cold start: load cookie → GET /api/auth/status.
  Future<void> bootstrap() async {
    bootstrapping = true;
    error = null;
    notifyListeners();
    try {
      final st = await _client.fetchAuthStatus();
      lastStatus = st;
      user = st.user;
    } catch (e) {
      // EDGE: offline / 5xx — stay logged out; keep local cookie for retry.
      error = e.toString();
      user = null;
    } finally {
      bootstrapping = false;
      notifyListeners();
    }
  }

  Future<void> loginEmail(String email, String password) async {
    await _runAuth(() => _client.loginEmail(email: email, password: password));
  }

  Future<void> registerEmail(String email, String password, {String name = ''}) async {
    await _runAuth(
      () => _client.registerEmail(email: email, password: password, name: name),
    );
  }

  /// Real Google Sign-In → server verifies id_token (not a mock).
  Future<void> loginGoogle() async {
    busy = true;
    error = null;
    notifyListeners();
    try {
      // Refresh provider flags / client_id
      try {
        lastStatus = await _client.fetchAuthStatus();
      } catch (_) {}
      if (lastStatus?.googleEnabled != true) {
        throw AsrApiException('Google login is disabled on the server', 503);
      }
      final cid = (lastStatus?.clientId ?? '').trim();
      if (cid.isEmpty) {
        throw AsrApiException('Google client_id missing from /api/auth/status', 503);
      }
      final token = await _googleTokens.obtainIdToken(serverClientId: cid);
      if (token == null || !isUsableGoogleCredential(token)) {
        throw AsrApiException('Google sign-in cancelled or no id_token', 401);
      }
      final cred = token.trim();
      await _runAuth(() => _client.loginGoogle(credential: cred));
    } on AsrApiException catch (e) {
      error = e.message;
      busy = false;
      notifyListeners();
      rethrow;
    } catch (e) {
      error = e.toString();
      busy = false;
      notifyListeners();
      rethrow;
    }
  }

  /// Kakao Custom Tab → HTTPS callback → deep link with asr_session (real OAuth).
  Future<void> loginKakao() async {
    busy = true;
    error = null;
    notifyListeners();
    try {
      try {
        lastStatus = await _client.fetchAuthStatus();
      } catch (_) {}
      if (lastStatus?.kakaoEnabled != true) {
        throw AsrApiException('Kakao login is disabled on the server', 503);
      }
      final start = _client.kakaoStartUrl(mode: 'login');
      final redirected = await _kakaoBrowser.authenticate(
        startUrl: start,
        callbackUrlScheme: kMobileOAuthScheme,
      );
      final parsed = parseKakaoDeepLink(redirected);
      if (!parsed.isSuccess) {
        throw AsrApiException(parsed.error ?? 'kakao_failed', 401);
      }
      await _runAuth(() => _client.applySessionToken(parsed.sessionToken!));
    } on AsrApiException catch (e) {
      error = e.message;
      busy = false;
      notifyListeners();
      rethrow;
    } catch (e) {
      error = e.toString();
      busy = false;
      notifyListeners();
      rethrow;
    }
  }

  Future<void> logout() async {
    busy = true;
    error = null;
    notifyListeners();
    try {
      await _client.logout();
    } catch (e) {
      // EDGE: network fail still clears local session in client.finally
      error = e.toString();
    } finally {
      user = null;
      busy = false;
      notifyListeners();
    }
  }

  Future<void> _runAuth(Future<AsrUser> Function() op) async {
    busy = true;
    error = null;
    notifyListeners();
    try {
      final u = await op();
      user = u;
      try {
        lastStatus = await _client.fetchAuthStatus();
        if (lastStatus?.user != null) user = lastStatus!.user;
      } catch (_) {
        // keep login user if status refresh fails
      }
    } on AsrApiException catch (e) {
      error = e.message;
      rethrow;
    } catch (e) {
      error = e.toString();
      rethrow;
    } finally {
      busy = false;
      notifyListeners();
    }
  }

  @override
  void dispose() {
    _client.close();
    super.dispose();
  }
}
