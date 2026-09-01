import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/services/evidence_bus.dart';
import 'package:sentence_reading/services/evidence_kinds.dart';

void main() {
  test('allowlist drops unknown kinds', () {
    final bus = EvidenceBus();
    bus.setEnabled(true);
    bus.record('not_a_real_kind', message: 'x');
    expect(bus.pendingCount, 0);
    bus.record('client_api_fail', message: '처리에 실패했습니다.', severity: 'error');
    expect(bus.pendingCount, 1);
    bus.dispose();
  });

  test('disabled bus is no-op', () {
    final bus = EvidenceBus();
    bus.setEnabled(false);
    bus.record('pref_translate_set', details: {'enabled': true});
    expect(bus.pendingCount, 0);
    bus.dispose();
  });

  test('kinds mirror includes reanalyze snapshot', () {
    expect(kEvidenceAllowedKinds.contains('reanalyze_pref_snapshot'), isTrue);
    expect(kEvidenceAllowedKinds.contains('figure_preserve_miss'), isTrue);
    expect(kEvidenceAllowedKinds.contains('stall_fired'), isTrue);
  });

  test('safe details keep bool/int snake keys', () {
    final bus = EvidenceBus();
    bus.setEnabled(true);
    bus.record(
      'reanalyze_pref_snapshot',
      severity: 'decision',
      details: {
        'want_translate_pref': true,
        'want_translate_sent': false,
        'auth_uid_present': true,
        'BadKey': 1,
        'CamelCase': 'nope',
      },
    );
    expect(bus.pendingCount, 1);
    bus.dispose();
  });
}
