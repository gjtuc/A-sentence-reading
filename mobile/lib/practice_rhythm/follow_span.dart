/// Follow-light span on the printed chunk (design/313).
library;

class FollowSpan {
  const FollowSpan({
    required this.start,
    required this.end,
    required this.weight,
    this.phone = '',
  });

  final int start;
  final int end;
  final int weight;
  final String phone;
}

/// Media-time position picks the printed span. Weight 0 spans are skipped.
FollowSpan? activeFollowSpan(
  List<FollowSpan> spans,
  int positionMs,
  int durationMs,
) {
  if (durationMs <= 0 || spans.isEmpty) return null;
  var total = 0;
  for (final s in spans) {
    if (s.weight > 0) total += s.weight;
  }
  if (total <= 0) return null;
  final target = positionMs / durationMs * total;
  var acc = 0.0;
  FollowSpan? last;
  for (final s in spans) {
    if (s.weight <= 0) continue;
    last = s;
    acc += s.weight;
    if (target < acc) return s;
  }
  return last;
}

/// The share of the audio in which the prompt finishes its walk down.
///
/// The bottom line has to be on screen before the voice reaches it, not as it
/// arrives, so the walk ends a little early.
const double kPromptScrollLead = 0.85;

/// One glide between two position ticks, so the walk reads as continuous.
const Duration kPromptScrollStep = Duration(milliseconds: 240);

/// Where the prompt stands when the audio is [position] into [duration].
///
/// Null while there is nothing to move: a sentence that already fits the screen
/// is left where it is. The caller must pass the player media clock, not a
/// rate-adjusted wall clock (design/313).
double? promptScrollTarget({
  required Duration position,
  required Duration duration,
  required double maxScrollExtent,
  double lead = kPromptScrollLead,
}) {
  if (maxScrollExtent <= 0 || lead <= 0) return null;
  final total = duration.inMilliseconds * lead;
  if (total <= 0) return null;
  final at = position.inMilliseconds / total;
  if (at <= 0) return 0;
  if (at >= 1) return maxScrollExtent;
  return maxScrollExtent * at;
}
