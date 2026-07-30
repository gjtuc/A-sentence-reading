/// Paper library JSON shapes from `/api/cache/papers*` (design/18 · design/62).
library;

/// One row from `GET /api/cache/papers`.
class PaperEntry {
  PaperEntry({
    required this.id,
    required this.title,
    this.source = 'pdf',
    this.updatedAt = '',
    this.sentenceCount = 0,
    this.figureCount = 0,
    this.debone = false,
    this.pipelineVersion = '',
    this.stale = false,
    this.hasSource = false,
  });

  /// Tolerant parse — never throws on partial/garbage maps.
  factory PaperEntry.fromJson(Map<String, dynamic>? json) {
    if (json == null) {
      return PaperEntry(id: '', title: '');
    }
    int asInt(Object? v) {
      if (v is int) return v;
      if (v is num) return v.toInt();
      return int.tryParse('$v') ?? 0;
    }

    return PaperEntry(
      id: '${json['id'] ?? ''}'.trim(),
      title: '${json['title'] ?? ''}'.trim(),
      source: '${json['source'] ?? 'pdf'}'.trim().isEmpty
          ? 'pdf'
          : '${json['source'] ?? 'pdf'}'.trim(),
      updatedAt: '${json['updated_at'] ?? ''}'.trim(),
      sentenceCount: asInt(json['sentence_count']),
      figureCount: asInt(json['figure_count']),
      debone: json['debone'] == true,
      pipelineVersion: '${json['pipeline_version'] ?? ''}'.trim(),
      stale: json['stale'] == true,
      hasSource: json['has_source'] == true,
    );
  }

  final String id;
  final String title;
  final String source;
  final String updatedAt;
  final int sentenceCount;
  final int figureCount;
  final bool debone;
  final String pipelineVersion;
  final bool stale;
  final bool hasSource;

  bool get isValid => id.isNotEmpty && title.isNotEmpty;

  String get subtitle {
    final bits = <String>[
      if (source.isNotEmpty) source,
      if (sentenceCount > 0) '문장 $sentenceCount',
      if (figureCount > 0) '그림 $figureCount',
      if (stale) '구버전',
    ];
    return bits.join(' · ');
  }
}

/// Minimal open result kept for the Reader tab until full reader lands.
class OpenedPaper {
  OpenedPaper({
    required this.sessionId,
    required this.cacheId,
    required this.title,
    this.sentenceCount = 0,
    this.figureCount = 0,
    this.warnings = const [],
  });

  factory OpenedPaper.fromOpenJson(
    Map<String, dynamic> json, {
    String fallbackTitle = '',
  }) {
    final sentences = json['sentences'];
    final figures = json['figures'];
    int countList(Object? v) => v is List ? v.length : 0;
    final warningsRaw = json['warnings'];
    final warnings = <String>[];
    if (warningsRaw is List) {
      for (final w in warningsRaw) {
        final s = '$w'.trim();
        if (s.isNotEmpty) warnings.add(s);
      }
    }
    return OpenedPaper(
      sessionId: '${json['session_id'] ?? ''}'.trim(),
      cacheId: '${json['cache_id'] ?? ''}'.trim(),
      title: '${json['title'] ?? fallbackTitle}'.trim(),
      sentenceCount: countList(sentences),
      figureCount: countList(figures),
      warnings: warnings,
    );
  }

  final String sessionId;
  final String cacheId;
  final String title;
  final int sentenceCount;
  final int figureCount;
  final List<String> warnings;

  bool get isValid => sessionId.isNotEmpty;
}
