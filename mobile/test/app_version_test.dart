import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/app_version.dart';

void main() {
  test('compareAppVersions orders semver segments', () {
    expect(compareAppVersions('0.3.93', '0.3.94'), -1);
    expect(compareAppVersions('0.3.94', '0.3.94'), 0);
    expect(compareAppVersions('0.3.95', '0.3.94'), 1);
    expect(compareAppVersions('0.3.9', '0.3.10'), -1);
  });

  test('isUpdateAvailable only when local older', () {
    expect(isUpdateAvailable('0.3.93', '0.3.94'), isTrue);
    expect(isUpdateAvailable('0.3.94', '0.3.94'), isFalse);
    expect(isUpdateAvailable('0.3.95', '0.3.94'), isFalse);
  });

  test('garbage versions fail closed', () {
    expect(compareAppVersions('', '0.3.94'), isNull);
    expect(compareAppVersions('0.3.94', 'bad'), isNull);
    expect(isUpdateAvailable('bad', '0.3.94'), isFalse);
  });
}
