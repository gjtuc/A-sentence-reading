/// design/284 — notify_complete_gate details builder (snake tokens only).
library;

/// Build details for `notify_complete_gate` (ints / snake strings only).
Map<String, Object> buildNotifyCompleteGateDetails({
  required bool handoffOk,
  required bool confirmOk,
  required String confirmVia,
  required String willNotify,
  required String pollCacheId,
  required bool listHasPollId,
  required bool diskHasPollId,
}) {
  final via = confirmVia.trim().toLowerCase();
  final viaTok = (via == 'list' || via == 'disk' || via == 'none') ? via : 'none';
  final notify = willNotify.trim().toLowerCase();
  final notifyTok = (notify == 'completed' || notify == 'failed' || notify == 'none')
      ? notify
      : 'none';
  final cid = pollCacheId.trim().toLowerCase().replaceAll(RegExp(r'[^a-z0-9]'), '');
  final out = <String, Object>{
    'handoff_ok': handoffOk ? 1 : 0,
    'confirm_ok': confirmOk ? 1 : 0,
    'confirm_via': viaTok,
    'will_notify': notifyTok,
    'list_has_poll_id': listHasPollId ? 1 : 0,
    'disk_has_poll_id': diskHasPollId ? 1 : 0,
  };
  if (cid.isNotEmpty) {
    out['poll_cache_id'] = 'c$cid';
  }
  return out;
}

/// Top-level ok for gate: completed notify requires handoff+confirm.
bool notifyCompleteGateOk({
  required bool handoffOk,
  required bool confirmOk,
  required String willNotify,
}) {
  final notify = willNotify.trim().toLowerCase();
  if (notify != 'completed') return true;
  return handoffOk && confirmOk;
}

String notifyCompleteGateCode({
  required bool handoffOk,
  required bool confirmOk,
  required String willNotify,
}) {
  final notify = willNotify.trim().toLowerCase();
  if (notify == 'completed' && !handoffOk) return 'notify_without_handoff';
  if (notify == 'completed' && !confirmOk) return 'notify_without_confirm';
  return 'ok';
}
