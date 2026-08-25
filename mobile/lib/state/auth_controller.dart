/// App-wide auth session (email · Google · Kakao · design/61·65).
library;

import 'package:flutter/foundation.dart';

import '../api/auth_models.dart';
import '../api/auth_deeplink.dart';
import '../api/client.dart';
import '../api/oauth_bridges.dart';
import '../api/oauth_models.dart';

/// Holds current [AsrUser] and drives login/register/logout/restore/OAuth.
class AuthController extends ChangeNotifier {
  AuthController({
    AsrClient? client,
    GoogleIdTokenSource? googleTokens,
    KakaoOAuthBrowser? kakaoBrowser,
    AuthDeepLinkBridge? deepLinks,
  })  : _client = client ?? AsrClient(),
        _googleTokens = googleTokens ?? GoogleSignInIdTokenSource(),
        _kakaoBrowser = kakaoBrowser ?? FlutterWebAuthKakaoBrowser(),
        _deepLinks = deepLinks ?? AuthDeepLinkBridge();

  final AsrClient _client;
  final GoogleIdTokenSource _googleTokens;
  final KakaoOAuthBrowser _kakaoBrowser;
  final AuthDeepLinkBridge _deepLinks;

  AsrClient get client => _client;

  AsrUser? user;
  AsrAuthStatus? lastStatus;
  bool bootstrapping = true;
  bool busy = false;
  String? error;
  /// design/77 — last magic-link request feedback (not a session).
  String? magicLinkHint;
  /// design/83 — server kill; missing/true → gate login. Fail-closed default.
  bool loginRequired = true;

  bool get isLoggedIn => user != null && !user!.isEmpty;

  /// On cold start: load cookie → GET /api/auth/status; wire magic deep link.
  Future<void> bootstrap() async {
    bootstrapping = true;
    error = null;
    notifyListeners();
    _deepLinks.setHandler(_onMagicLink);
    await _deepLinks.start();
    try {
      final st = await _client.fetchAuthStatus();
      lastStatus = st;
      user = st.user;
      try {
        final status = await _client.fetchStatus();
        loginRequired = status.mobileLoginRequired;
      } catch (_) {
        // EDGE: status fetch fail → keep require-login (fail-closed).
        loginRequired = true;
      }
    } catch (e) {
      // EDGE: offline / 5xx — stay logged out; keep local cookie for retry.
      error = e.toString();
      user = null;
      loginRequired = true;
    } finally {
      bootstrapping = false;
      notifyListeners();
    }
  }

  Future<void> _onMagicLink({String? token, String? error}) async {
    final err = (error ?? '').trim();
    if (err.isNotEmpty) {
      this.error = _describeMagicError(err);
      notifyListeners();
      return;
    }
    final t = (token ?? '').trim();
    if (t.isEmpty) return;
    try {
      await _runAuth(() => _client.applySessionToken(t));
    } catch (e) {
      this.error = e.toString();
      notifyListeners();
    }
  }

  String _describeMagicError(String code) {
    switch (code) {
      case 'expired':
        return '로그인 링크가 만료되었습니다. 다시 요청하세요.';
      case 'used':
        return '이미 사용된 로그인 링크입니다. 다시 요청하세요.';
      case 'bad_token':
      case 'missing_session':
        return '로그인 링크가 올바르지 않습니다.';
      case 'magic_disabled':
        return '이메일 로그인 링크가 꺼져 있습니다.';
      default:
        return '로그인 링크를 처리하지 못했습니다.';
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

  /// design/77 — request SMTP magic link (does not set session by itself).
  Future<void> requestMagicLink(String email) async {
    busy = true;
    error = null;
    magicLinkHint = null;
    notifyListeners();
    try {
      try {
        lastStatus = await _client.fetchAuthStatus();
      } catch (_) {}
      // Missing flag → treat as on for sideload before CD; explicit false hides.
      final st = await _client.fetchStatus();
      if (!st.mobileEmailMagicLink) {
        throw AsrApiException('이메일 로그인 링크가 꺼져 있습니다.', 503);
      }
      magicLinkHint = await _client.requestMagicLink(email: email);
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

  /// Google native Sign-In with account chooser every time (design/65).
  ///
  /// WHY signOut-before-signIn: after the first success Google skipped the
  /// picker and reused the last account — blocked admin vs other switches.
  /// Custom Tab GIS remains fallback when Android SHA-1 is missing
  /// (DEVELOPER_ERROR / ApiException 10).
  Future<void> loginGoogle() async {
    busy = true;
    error = null;
    notifyListeners();
    try {
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
      try {
        final token = await _googleTokens.obtainIdToken(serverClientId: cid);
        if (token != null && isUsableGoogleCredential(token)) {
          await _runAuth(
            () => _client.loginGoogle(credential: token.trim()),
          );
          return;
        }
        // EDGE: user cancelled native picker — stay logged out, no Custom Tab.
        throw AsrApiException('Google sign-in cancelled or no id_token', 401);
      } catch (e) {
        if (e is AsrApiException) rethrow;
        if (!_isGoogleDeveloperError(e)) rethrow;
        // Fallback: Cloud Run GIS (authorized JS origin; no Android SHA-1).
        final start = _client.googleMobileStartUrl(mode: 'login');
        final redirected = await _kakaoBrowser.authenticate(
          startUrl: start,
          callbackUrlScheme: kMobileOAuthScheme,
        );
        final parsed = parseGoogleDeepLink(redirected);
        if (!parsed.isSuccess) {
          throw AsrApiException(parsed.error ?? 'google_failed', 401);
        }
        await _runAuth(() => _client.applySessionToken(parsed.sessionToken!));
      }
    } on AsrApiException catch (e) {
      error = e.message;
      busy = false;
      notifyListeners();
      rethrow;
    } catch (e) {
      error = describeGoogleSignInFailure(e);
      busy = false;
      notifyListeners();
      rethrow;
    }
  }

  static bool _isGoogleDeveloperError(Object error) {
    final lower = error.toString().toLowerCase();
    return lower.contains('developer_error') ||
        (lower.contains('sign_in_failed') &&
            (lower.contains(', 10,') ||
                lower.contains(': 10') ||
                lower.contains('apiexception: 10')));
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
