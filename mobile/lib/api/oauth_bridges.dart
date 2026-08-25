/// Platform OAuth bridges (design/65). Default impls use plugins; tests inject fakes.
library;

import 'package:flutter_web_auth_2/flutter_web_auth_2.dart';
import 'package:google_sign_in/google_sign_in.dart';

import 'oauth_models.dart';

/// Obtains a Google ID token for `POST /api/auth/google`.
abstract class GoogleIdTokenSource {
  Future<String?> obtainIdToken({required String serverClientId});
}

class GoogleSignInIdTokenSource implements GoogleIdTokenSource {
  GoogleSignInIdTokenSource({GoogleSignIn? signIn}) : _signIn = signIn;

  GoogleSignIn? _signIn;

  @override
  Future<String?> obtainIdToken({required String serverClientId}) async {
    final cid = serverClientId.trim();
    if (cid.isEmpty) return null;
    final gi = _signIn ??
        GoogleSignIn(
          scopes: const ['email', 'profile'],
          serverClientId: cid,
        );
    _signIn = gi;
    // WHY: without signOut, Google reuses the last account and skips the
    // chooser — admins cannot switch to another Google identity (design/65).
    try {
      await gi.signOut();
    } catch (_) {
      // EDGE: no prior session / Play Services flake — still attempt signIn.
    }
    final account = await gi.signIn();
    if (account == null) return null; // EDGE: user cancelled
    final auth = await account.authentication;
    final token = auth.idToken;
    if (!isUsableGoogleCredential(token)) return null;
    return token!.trim();
  }
}

/// Opens Kakao start URL and returns the final deep-link redirect.
abstract class KakaoOAuthBrowser {
  Future<String> authenticate({
    required String startUrl,
    required String callbackUrlScheme,
  });
}

class FlutterWebAuthKakaoBrowser implements KakaoOAuthBrowser {
  @override
  Future<String> authenticate({
    required String startUrl,
    required String callbackUrlScheme,
  }) {
    return FlutterWebAuth2.authenticate(
      url: startUrl,
      callbackUrlScheme: callbackUrlScheme,
    );
  }
}
