import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/screens/login_screen.dart';

void main() {
  test('validateRegisterPasswords accepts matching long password', () {
    expect(validateRegisterPasswords('password1', 'password1'), isNull);
  });

  test('EDGE: short password', () {
    expect(
      validateRegisterPasswords('short', 'short'),
      '비밀번호는 8자 이상이어야 합니다.',
    );
  });

  test('EDGE: mismatch', () {
    expect(
      validateRegisterPasswords('password1', 'password2'),
      '비밀번호 확인이 일치하지 않습니다.',
    );
  });

  test('EDGE: empty confirm mismatches', () {
    expect(
      validateRegisterPasswords('password1', ''),
      '비밀번호 확인이 일치하지 않습니다.',
    );
  });
}
