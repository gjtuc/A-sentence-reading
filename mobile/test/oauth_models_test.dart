import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/oauth_models.dart';

void main() {
  group('parseKakaoDeepLink', () {
    test('success', () {
      final r = parseKakaoDeepLink(
        'com.gjtuc.sentence_reading://oauth/kakao?asr_session=tok.abc&auth=logged_in',
      );
      expect(r.isSuccess, isTrue);
      expect(r.sessionToken, 'tok.abc');
      expect(r.auth, 'logged_in');
    });

    test('edges', () {
      expect(parseKakaoDeepLink(null).error, 'empty_redirect');
      expect(parseKakaoDeepLink('').error, 'empty_redirect');
      expect(parseKakaoDeepLink('https://example.com/x').error, 'bad_scheme');
      expect(
        parseKakaoDeepLink('com.gjtuc.sentence_reading://other/kakao?asr_session=x')
            .error,
        'bad_host',
      );
      expect(
        parseKakaoDeepLink('com.gjtuc.sentence_reading://oauth/nope?asr_session=x')
            .error,
        'bad_path',
      );
      expect(
        parseKakaoDeepLink(
          'com.gjtuc.sentence_reading://oauth/kakao?auth_error=bad_state',
        ).error,
        'bad_state',
      );
      expect(
        parseKakaoDeepLink('com.gjtuc.sentence_reading://oauth/kakao?asr_session=').error,
        'missing_session',
      );
      expect(
        parseKakaoDeepLink(
          'com.gjtuc.sentence_reading://oauth/kakao?asr_session=deleted',
        ).error,
        'missing_session',
      );
    });
  });

  group('parseMagicDeepLink', () {
    test('success', () {
      final r = parseMagicDeepLink(
        'com.gjtuc.sentence_reading://oauth/magic?asr_session=tok.xyz&auth=magic',
      );
      expect(r.isSuccess, isTrue);
      expect(r.sessionToken, 'tok.xyz');
      expect(r.auth, 'magic');
    });

    test('wrong path is kakao-only failure', () {
      expect(
        parseMagicDeepLink(
          'com.gjtuc.sentence_reading://oauth/kakao?asr_session=x',
        ).error,
        'bad_path',
      );
    });
  });

  group('parseGoogleDeepLink', () {
    test('parses Custom Tab bounce', () {
      final r = parseGoogleDeepLink(
        'com.gjtuc.sentence_reading://oauth/google?asr_session=tok.g&auth=google',
      );
      expect(r.isSuccess, isTrue);
      expect(r.sessionToken, 'tok.g');
      expect(r.auth, 'google');
    });
  });

  group('isUsableGoogleCredential', () {
    test('edges', () {
      expect(isUsableGoogleCredential(null), isFalse);
      expect(isUsableGoogleCredential(''), isFalse);
      expect(isUsableGoogleCredential('null'), isFalse);
      expect(isUsableGoogleCredential('a.b'), isFalse);
      expect(isUsableGoogleCredential('a.b.c'), isFalse); // too short
      expect(
        isUsableGoogleCredential('aaa.bbb.ccc.ddd.eee.fff'),
        isTrue,
      );
    });
  });

  group('describeGoogleSignInFailure', () {
    test('developer_error / code 10 fail-closed', () {
      final msg = describeGoogleSignInFailure(
        Exception(
          'PlatformException(sign_in_failed, com.google.android.gms.common.api.ApiException: 10: , null, null)',
        ),
      );
      expect(msg.contains('설정이 아직'), isTrue);
      expect(msg.toLowerCase().contains('platformexception'), isFalse);
    });

    test('does not echo long / auth-like dumps', () {
      final long = 'Authorization: Bearer ' + List.filled(200, 'x').join();
      final msg = describeGoogleSignInFailure(Exception(long));
      expect(msg, 'Google 로그인에 실패했습니다.');
      expect(msg.toLowerCase().contains('bearer'), isFalse);
    });
  });

}
