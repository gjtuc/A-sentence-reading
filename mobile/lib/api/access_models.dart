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
    this.isAdmin = false,
    this.effective = '',
    this.invitePoolReady = false,
    this.decisionNote = '',
  });

  factory AccessStatus.fromJson(Map<String, dynamic>? json) {
    if (json == null) {
      // EDGE: missing payload → treat as non-admin (fail-closed for admin chrome).
      return AccessStatus(
        gateEnabled: false,
        status: 'none',
        canUsePaid: true,
        isAdmin: false,
      );
    }
    return AccessStatus(
      gateEnabled: json['gate_enabled'] == true,
      status: '${json['status'] ?? 'none'}'.trim().isEmpty
          ? 'none'
          : '${json['status']}'.trim(),
      canUsePaid: json['can_use_paid'] == true,
      // EDGE: only explicit true counts — missing/false → hide admin UI.
      isAdmin: json['is_admin'] == true,
      effective: '${json['effective'] ?? ''}',
      invitePoolReady: json['invite_pool_ready'] == true,
      decisionNote: '${json['decision_note'] ?? ''}',
    );
  }

  final bool gateEnabled;
  final String status;
  final bool canUsePaid;
  /// Server-attested admin email membership (ASR_ADMIN_EMAILS). Not a client trust.
  final bool isAdmin;
  final String effective;
  final bool invitePoolReady;
  final String decisionNote;

  bool get isPending => status == 'pending';
  bool get isAllowed => status == 'allowed' || effective == 'admin';
  bool get isDenied => status == 'denied';
}

/// Whether Settings should show the invite-code redeem field (design/104).
///
/// WHY: approved users and admins do not redeem; none/pending/denied still may
/// (Deny re-enter). Waiting shell ([84]) is the primary path; Settings is fallback.
///
/// FAIL-CLOSED UI: unknown [access] → hide field (no flash of redeem for allowed).
bool shouldShowSettingsInviteRedeem(AccessStatus? access) {
  if (access == null) return false;
  // EDGE: admin already can_use_paid via effective=admin — no self-redeem needed.
  if (access.isAdmin) return false;
  // EDGE: gate off → paid open for everyone; invite UI is noise.
  if (!access.gateEnabled) return false;
  // Allowed (or equivalent paid unlock) → hide.
  if (access.canUsePaid || access.status == 'allowed') return false;
  // none / pending / denied → show (Deny = re-enter per product).
  return true;
}
