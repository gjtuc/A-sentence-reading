import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/access_models.dart';

void main() {
  group('normalizeInviteCodeInput', () {
    test('happy', () {
      expect(normalizeInviteCodeInput('TqG3-V12T'), 'TQG3V12T');
      expect(normalizeInviteCodeInput('tq g3 v12t'), 'TQG3V12T');
    });
    test('edges', () {
      expect(normalizeInviteCodeInput(null), '');
      expect(normalizeInviteCodeInput(''), '');
      expect(normalizeInviteCodeInput('!!!'), '');
      expect(isPlausibleInviteCode('AB'), isFalse);
      expect(isPlausibleInviteCode('ABCD-EFGH'), isTrue);
    });
  });

  group('AccessStatus.fromJson', () {
    test('null and partial', () {
      final a = AccessStatus.fromJson(null);
      expect(a.canUsePaid, isTrue);
      final b = AccessStatus.fromJson({
        'gate_enabled': true,
        'status': 'pending',
        'can_use_paid': false,
      });
      expect(b.isPending, isTrue);
      expect(b.canUsePaid, isFalse);
    });
  });

  test('AccessStatus isAdmin fail-closed defaults', () {
    final missing = AccessStatus.fromJson(null);
    expect(missing.isAdmin, isFalse);
    final plain = AccessStatus.fromJson({
      'gate_enabled': true,
      'status': 'none',
      'can_use_paid': false,
    });
    expect(plain.isAdmin, isFalse);
    final admin = AccessStatus.fromJson({
      'gate_enabled': true,
      'status': 'allowed',
      'can_use_paid': true,
      'is_admin': true,
      'effective': 'admin',
    });
    expect(admin.isAdmin, isTrue);
  });
}
