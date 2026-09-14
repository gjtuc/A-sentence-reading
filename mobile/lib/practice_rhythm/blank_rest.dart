/// design/274 — blank rest after successful Replay (15/N × step).
library;

/// Pref key — Settings + practice screen (default on).
const String kBlankRestPrefKey = 'asr.practice.blank_rest';

/// Rest after finishing step [step1Based] of [chunkCountN] (1-based).
/// Full sentence N=1 → 15s. Round to nearest millisecond.
Duration blankRestDuration({
  required int chunkCountN,
  required int step1Based,
}) {
  if (chunkCountN <= 0 || step1Based <= 0) return Duration.zero;
  final n = chunkCountN;
  final k = step1Based > n ? n : step1Based;
  final ms = (15000.0 * k / n).round();
  if (ms <= 0) return Duration.zero;
  return Duration(milliseconds: ms);
}
