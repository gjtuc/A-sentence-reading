import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/pdf/normalize_pairing_key.dart';

void main() {
  test('normalizePairingKey strips articles like Python twin', () {
    const a =
        'The selective hydrogenation of acetylene over Ni/Cu catalysts';
    const b =
        'selective hydrogenation of acetylene over Ni/Cu catalysts';
    expect(normalizePairingKey(a), normalizePairingKey(b));
    expect(normalizePairingKey(a).contains(' the '), isFalse);
  });

  test('normalizePairingKey strips SI prefix', () {
    // Mirror tests/test_supplementary_pairing.py (colon folded by title key).
    const base =
        'Nickel copper alloy methane dry reforming study title long enough';
    const withSi =
        'Supporting Information: Nickel copper alloy methane dry reforming study title long enough';
    expect(normalizePairingKey(withSi), normalizePairingKey(base));
  });

  test('normalizeTitleKey folds case and punct', () {
    expect(
      normalizeTitleKey('Hello, World!'),
      normalizeTitleKey('hello world'),
    );
  });
}
