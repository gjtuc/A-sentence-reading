import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/auth_models.dart';
import 'package:sentence_reading/api/session_store.dart';

void main() {
  group('parseAsrSessionCookie', () {
    test('happy path with attributes', () {
      expect(
        parseAsrSessionCookie(
          'asr_session=tok_abc; Path=/; HttpOnly; SameSite=Lax',
        ),
        'tok_abc',
      );
    });

    test('edge null empty deleted wrong name', () {
      expect(parseAsrSessionCookie(null), isNull);
      expect(parseAsrSessionCookie(''), isNull);
      expect(parseAsrSessionCookie('   '), isNull);
      expect(parseAsrSessionCookie('asr_session=deleted'), isNull);
      expect(parseAsrSessionCookie('asr_session='), isNull);
      expect(parseAsrSessionCookie('other=tok; Path=/'), isNull);
      expect(parseAsrSessionCookie('session=tok'), isNull);
    });

    test('edge quoted and joined cookies', () {
      expect(parseAsrSessionCookie('asr_session="quoted_tok"; Path=/'), 'quoted_tok');
      expect(
        parseAsrSessionCookie('foo=1; asr_session=mid; bar=2'),
        'mid',
      );
    });
  });

  group('MemorySessionStore', () {
    test('write read clear and empty whitespace', () async {
      final s = MemorySessionStore();
      expect(await s.readToken(), isNull);
      await s.writeToken('  abc  ');
      expect(await s.readToken(), 'abc');
      await s.writeToken('   ');
      expect(await s.readToken(), isNull);
      await s.writeToken('x');
      await s.clear();
      expect(await s.readToken(), isNull);
    });
  });

  group('AsrUser / AsrAuthStatus parse', () {
    test('tolerant missing keys', () {
      final u = AsrUser.fromJson({});
      expect(u.isEmpty, isTrue);
      final u2 = AsrUser.fromJson({
        'uid': 'u1',
        'email': 'a@b.c',
        'providers': ['email', 'google'],
      });
      expect(u2.displayLabel, 'a@b.c');
      expect(u2.providers, ['email', 'google']);

      final st = AsrAuthStatus.fromJson({
        'ok': true,
        'auth_enabled': true,
        'providers': {'email': true, 'google': false},
        'user': {'uid': 'u1', 'email': 'a@b.c'},
      });
      expect(st.emailEnabled, isTrue);
      expect(st.user?.uid, 'u1');

      // EDGE: providers as map of booleans on user
      final u3 = AsrUser.fromJson({
        'uid': 'x',
        'providers': {'email': true, 'kakao': false},
      });
      expect(u3.providers, ['email']);
    });
  });
}
