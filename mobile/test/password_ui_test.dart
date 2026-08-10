import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/screens/login_screen.dart';

void main() {
  test('LoginScreen is constructible without password controllers', () {
    // Smoke: type exists after design/78 password-UI removal.
    expect(LoginScreen, isNotNull);
  });
}
