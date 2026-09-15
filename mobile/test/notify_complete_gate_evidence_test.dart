import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/services/notify_complete_gate_evidence.dart';

void main() {
  test('notify_complete_gate details shape', () {
    final d = buildNotifyCompleteGateDetails(
      handoffOk: false,
      confirmOk: true,
      confirmVia: 'disk',
      willNotify: 'completed',
      pollCacheId: '45efe205811d',
      listHasPollId: false,
      diskHasPollId: true,
    );
    expect(d['handoff_ok'], 0);
    expect(d['confirm_ok'], 1);
    expect(d['confirm_via'], 'disk');
    expect(d['will_notify'], 'completed');
    expect(d['poll_cache_id'], 'c45efe205811d');
    expect(d['list_has_poll_id'], 0);
    expect(d['disk_has_poll_id'], 1);
    expect(
      notifyCompleteGateOk(
        handoffOk: false,
        confirmOk: true,
        willNotify: 'completed',
      ),
      isFalse,
    );
    expect(
      notifyCompleteGateCode(
        handoffOk: false,
        confirmOk: true,
        willNotify: 'completed',
      ),
      'notify_without_handoff',
    );
  });
}
