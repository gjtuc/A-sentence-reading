/// Access-gate JSON helpers (design/67).
library;

/// Normalize user-typed OTP invite to 8 A-Z/2-9 chars (no dash).
String normalizeInviteCodeInput(String? raw) {
  if (raw == null) return '';
  final buf = StringBuffer();
  for (final rune in raw.toUpperCase().runes) {
    final ch = String.fromCharCode(rune);
    if (RegExp(r'[A-Z0-9]').hasMatch(ch)) {
      // Drop ambiguous visually? Server accepts full alnum; we keep digits.
      buf.write(ch);
    }
  }
  return buf.toString();
}

/// True when length is exactly 8 after normalize (XXXX-XXXX).
bool isPlausibleInviteCode(String? raw) {
  return normalizeInviteCodeInput(raw).length == 8;
}

class AccessStatus {
  AccessStatus({
    required this.gateEnabled,
    required this.status,
    required this.canUsePaid,
    this.effective = '',
    this.invitePoolReady = false,
    this.decisionNote = '',
  });

  factory AccessStatus.fromJson(Map<String, dynamic>? json) {
    if (json == null) {
      return AccessStatus(
        gateEnabled: false,
        status: 'none',
        canUsePaid: true,
      );
    }
    return AccessStatus(
      gateEnabled: json['gate_enabled'] == true,
      status: '${json['status'] ?? 'none'}'.trim().isEmpty
          ? 'none'
          : '${json['status']}'.trim(),
      canUsePaid: json['can_use_paid'] == true,
      effective: '${json['effective'] ?? ''}',
      invitePoolReady: json['invite_pool_ready'] == true,
      decisionNote: '${json['decision_note'] ?? ''}',
    );
  }

  final bool gateEnabled;
  final String status;
  final bool canUsePaid;
  final String effective;
  final bool invitePoolReady;
  final String decisionNote;

  bool get isPending => status == 'pending';
  bool get isAllowed => status == 'allowed' || effective == 'admin';
  bool get isDenied => status == 'denied';
}
