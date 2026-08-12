/// design/123 — validate stored sentence/figure indices (fail-closed).
library;

/// Result of validating a stored progress row against a paper's counts.
class ProgressValidation {
  const ProgressValidation._({
    required this.ok,
    this.sentenceIndex,
    this.figureIndex,
    this.error,
  });

  factory ProgressValidation.ok({
    required int sentenceIndex,
    required int figureIndex,
  }) =>
      ProgressValidation._(
        ok: true,
        sentenceIndex: sentenceIndex,
        figureIndex: figureIndex,
      );

  factory ProgressValidation.invalid(String error) =>
      ProgressValidation._(ok: false, error: error);

  final bool ok;
  final int? sentenceIndex;
  final int? figureIndex;
  final String? error;
}

int? _asInt(Object? v) {
  if (v is int) return v;
  if (v is num && v == v.roundToDouble()) return v.toInt();
  if (v is String) {
    final t = v.trim();
    if (RegExp(r'^-?\d+$').hasMatch(t)) return int.parse(t);
  }
  return null;
}

/// WHY: product 4B — refuse open when stored progress cannot be applied exactly.
///
/// Rules:
/// - [sentenceCount] must be >= 1
/// - sentence/figure must be integers
/// - 0 <= sentence < sentenceCount
/// - if figureCount == 0: figure must be 0
/// - else 0 <= figure < figureCount
ProgressValidation validateProgressIndices({
  required Object? sentenceIndex,
  required Object? figureIndex,
  required int sentenceCount,
  required int figureCount,
}) {
  if (sentenceCount < 1) {
    return ProgressValidation.invalid('empty_sentences');
  }
  final si = _asInt(sentenceIndex);
  final fi = _asInt(figureIndex);
  if (si == null || fi == null) {
    return ProgressValidation.invalid('non_integer_index');
  }
  if (si < 0 || si >= sentenceCount) {
    return ProgressValidation.invalid('sentence_out_of_range');
  }
  if (figureCount <= 0) {
    if (fi != 0) {
      return ProgressValidation.invalid('figure_out_of_range');
    }
  } else if (fi < 0 || fi >= figureCount) {
    return ProgressValidation.invalid('figure_out_of_range');
  }
  return ProgressValidation.ok(sentenceIndex: si, figureIndex: fi);
}

String progressPrefsKey(String? uid) {
  final u = (uid ?? '').trim().replaceAll(RegExp(r'[^A-Za-z0-9_\-]'), '');
  if (u.isEmpty) return 'asr.progress.v1';
  final safe = u.length > 128 ? u.substring(0, 128) : u;
  return 'asr.progress.v1.u.$safe';
}
