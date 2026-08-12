/// design/120 — when replay / retry-speak controls may run.
library;

/// True only when a local take path is present and non-empty.
///
/// WHY: 「다시 듣기」 must not pretend success with no recording (fail-closed).
bool canReplayShadowingTake(String? localPath) {
  final p = (localPath ?? '').trim();
  return p.isNotEmpty;
}
