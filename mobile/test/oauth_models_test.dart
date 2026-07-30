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
}
