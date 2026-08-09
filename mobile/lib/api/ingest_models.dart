/// Models for mobile PDF ingest (design/70).
library;

/// Successful ingest poll result (fail-closed: require cache id when possible).
class IngestJobResult {
  IngestJobResult({
    required this.jobId,
    this.cacheId = '',
    this.sessionId = '',
    this.title = '',
    this.percent = 100,
  });

  final String jobId;
  final String cacheId;
  final String sessionId;
  final String title;
  final int percent;

  bool get hasCacheId => cacheId.trim().isNotEmpty;
}
