/// Pure OAuth helpers for Flutter Google/Kakao (design/65).
///
/// WHY separate from plugins: unit-test deep-link parse + token refuse
/// without Google Play / Custom Tabs.
library;

/// Android OAuth URI scheme (must match AndroidManifest + server deep link).
///
/// WHY (146c): flutter_web_auth_2 v4 allows `[a-z\d+.-]` only — no underscore.
/// applicationId remains `com.gjtuc.sentence_reading`.
const String kMobileOAuthScheme = 'com.gjtuc.sentence-reading';

/// Full deep-link prefix used by the server (host oauth, path /kakao).
const String kMobileKakaoDeepLink = '$kMobileOAuthScheme://oauth/kakao';

/// design/77 — email magic-link bounce into the app.
const String kMobileMagicDeepLink = '$kMobileOAuthScheme://oauth/magic';

/// Result of parsing a Kakao / magic mobile deep link.
class KakaoDeepLinkResult {
  const KakaoDeepLinkResult({this.sessionToken, this.auth, this.error});

  final String? sessionToken;
  final String? auth;
  final String? error;

  bool get isSuccess =>
      (error == null || error!.trim().isEmpty) &&
      sessionToken != null &&
      sessionToken!.trim().isNotEmpty;
}

/// Parse com.gjtuc.sentence_reading://oauth/kakao?...
///
/// EDGE: null/empty/wrong scheme/host -> failure; blank asr_session -> failure.
///
/// NOTE: Dart Uri.tryParse rejects some dotted custom schemes as invalid;
/// we parse manually for the known Android callback shape.
KakaoDeepLinkResult parseKakaoDeepLink(String? raw) {
  return parseOAuthDeepLink(raw, expectedPath: 'kakao');
}

/// Parse com.gjtuc.sentence_reading://oauth/magic?...
KakaoDeepLinkResult parseMagicDeepLink(String? raw) {
  return parseOAuthDeepLink(raw, expectedPath: 'magic');
}

/// Parse com.gjtuc.sentence_reading://oauth/google?... (Custom Tab GIS).
KakaoDeepLinkResult parseGoogleDeepLink(String? raw) {
  return parseOAuthDeepLink(raw, expectedPath: 'google');
}

/// Shared custom-scheme OAuth/magic parse (design/65 · design/77).
KakaoDeepLinkResult parseOAuthDeepLink(
  String? raw, {
  required String expectedPath,
}) {
  final s = (raw ?? '').trim();
  if (s.isEmpty) {
    return const KakaoDeepLinkResult(error: 'empty_redirect');
  }

  const prefix = '$kMobileOAuthScheme://';
  if (!s.startsWith(prefix)) {
    return const KakaoDeepLinkResult(error: 'bad_scheme');
  }
  final rest = s.substring(prefix.length);
  final qAt = rest.indexOf('?');
  final pathPart = qAt < 0 ? rest : rest.substring(0, qAt);
  final queryPart = qAt < 0 ? '' : rest.substring(qAt + 1);

  // Expect host/path: oauth/{kakao|magic|google}
  final norm = pathPart.startsWith('/') ? pathPart.substring(1) : pathPart;
  final segments = norm.split('/').where((e) => e.isNotEmpty).toList();
  if (segments.length < 2 || segments[0] != 'oauth') {
    return const KakaoDeepLinkResult(error: 'bad_host');
  }
  if (segments[1] != expectedPath) {
    return const KakaoDeepLinkResult(error: 'bad_path');
  }

  final params = <String, String>{};
  if (queryPart.isNotEmpty) {
    for (final part in queryPart.split('&')) {
      if (part.isEmpty) continue;
      final eq = part.indexOf('=');
      final k = eq < 0 ? part : part.substring(0, eq);
      final v = eq < 0 ? '' : part.substring(eq + 1);
      params[Uri.decodeQueryComponent(k)] = Uri.decodeQueryComponent(v);
    }
  }

  final err = (params['auth_error'] ?? '').trim();
  if (err.isNotEmpty) {
    return KakaoDeepLinkResult(error: err);
  }
  final token = (params['asr_session'] ?? '').trim();
  if (token.isEmpty || token.toLowerCase() == 'deleted') {
    return const KakaoDeepLinkResult(error: 'missing_session');
  }
  final auth = (params['auth'] ?? '').trim();
  return KakaoDeepLinkResult(
    sessionToken: token,
    auth: auth.isEmpty ? null : auth,
  );
}

/// True when a Google id_token / credential string is usable.
bool isUsableGoogleCredential(String? raw) {
  if (raw == null) return false;
  final t = raw.trim();
  if (t.isEmpty) return false;
  final lower = t.toLowerCase();
  if (lower == 'null' || lower == 'undefined') return false;
  // JWT has two dots; EDGE: refuse obviously truncated values
  if (t.split('.').length < 3) return false;
  return t.length >= 20;
}

/// Map plugin/platform Google Sign-In failures to a safe Korean message.
///
/// WHY: ApiException 10 / DEVELOPER_ERROR means package+SHA-1 are not registered
/// in Google Cloud. Fail-closed: never imply login succeeded; never echo tokens.
///
/// EDGE: cancel/empty id_token is handled before this; network vs config separated.
String describeGoogleSignInFailure(Object error) {
  final s = error.toString();
  final lower = s.toLowerCase();
  // Google Play Services: PlatformException(sign_in_failed, ... ApiException: 10 ...)
  final isDeveloper = lower.contains('developer_error') ||
      (lower.contains('sign_in_failed') &&
          (lower.contains(', 10,') ||
              lower.contains(': 10') ||
              lower.contains('apiexception: 10')));
  if (isDeveloper) {
    return 'Google 로그인 설정이 아직 안 됐습니다. '
        'Google Cloud에 Android OAuth 클라이언트를 만들고 '
        '패키지(com.gjtuc.sentence_reading)와 사이드로드용 SHA-1을 등록하세요. (design/65)';
  }
  if (lower.contains('network_error') ||
      lower.contains('socketexception') ||
      lower.contains('failed host lookup')) {
    return '네트워크 오류로 Google 로그인을 완료하지 못했습니다.';
  }
  // EDGE: keep UI short; avoid dumping long traces / cookie-like strings
  if (s.length > 160 ||
      lower.contains('authorization') ||
      lower.contains('bearer ')) {
    return 'Google 로그인에 실패했습니다.';
  }
  return 'Google 로그인에 실패했습니다.';
}

