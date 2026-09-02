/// Models for mobile PDF ingest (design/70 · design/71).
library;

/// Successful ingest poll result (fail-closed: require cache id when possible).
class IngestJobResult {
  IngestJobResult({
    required this.jobId,
    this.cacheId = '',
    this.sessionId = '',
    this.title = '',
    this.percent = 100,
    this.contentHash = '',
    this.harmonizePending = false,
    this.harmonizeTotal = 0,
    this.harmonizeDone = 0,
    this.harmonizeFailed = 0,
    this.harmonizeAttemptN = 0,
  });

  final String jobId;
  final String cacheId;
  final String sessionId;
  final String title;
  final int percent;
  final String contentHash;
  /// design/169o — post-ingest 재감수 residual (from job result).
  final bool harmonizePending;
  final int harmonizeTotal;
  final int harmonizeDone;
  final int harmonizeFailed;
  final int harmonizeAttemptN;

  bool get hasCacheId => cacheId.trim().isNotEmpty;
}
