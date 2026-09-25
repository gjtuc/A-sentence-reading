/// design/364 — marks a take as belonging to a sample round.
///
/// The server keeps audio only for tagged takes, so an untagged practice take
/// stays as it is today: heard, scored, then dropped.
library;

class SampleTakeTag {
  const SampleTakeTag({
    required this.round,
    required this.lineId,
    required this.chunkIndex,
    required this.tier,
    required this.density,
    this.voice = '',
    this.rate = 0,
  });

  final int round;

  /// Sentence id of the sample line, e.g. `sent_f01`.
  final String lineId;
  final int chunkIndex;
  final int tier;
  final int density;

  /// Voice and playback rate actually heard, not the ones asked for.
  final String voice;
  final double rate;

  bool get isValid => round >= 1 && round <= 10 && lineId.trim().isNotEmpty;

  Map<String, String> formFields() => {
        'sample_round': '$round',
        'sample_line': lineId.trim(),
        'sample_chunk': '$chunkIndex',
        'skill_tier': '$tier',
        'skill_density': '$density',
        'tts_voice': voice.trim(),
        'tts_rate': rate.toStringAsFixed(3),
      };
}
