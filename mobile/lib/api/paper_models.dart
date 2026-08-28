/// Paper library JSON shapes from `/api/cache/papers*` (design/18 · design/62 · 152).
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
    this.expiresAt = '',
    this.retentionWarn = false,
    this.retentionCanExtend = false,
    this.retentionDaysUntilExpiry,
    this.retentionExtendDays = 90,
    this.docRole = 'main',
    this.libraryTag = '',
    this.ingestStatus = 'ok',
    this.canMergeSupplementary = false,
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

    final docRole = '${json['doc_role'] ?? 'main'}'.trim().isEmpty
        ? 'main'
        : '${json['doc_role'] ?? 'main'}'.trim();
    var libraryTag = '${json['library_tag'] ?? ''}'.trim();
    if (libraryTag.isEmpty) {
      libraryTag = _defaultTag(docRole);
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
      expiresAt: '${json['expires_at'] ?? ''}'.trim(),
      retentionWarn: _retentionBool(json['retention'], 'warn'),
      retentionCanExtend: _retentionBool(json['retention'], 'can_extend'),
      retentionDaysUntilExpiry: _retentionInt(json['retention'], 'days_until_expiry'),
      retentionExtendDays: _retentionInt(json['retention'], 'extend_days') ?? 90,
      docRole: docRole,
      libraryTag: libraryTag,
      ingestStatus: '${json['ingest_status'] ?? 'ok'}'.trim().isEmpty
          ? 'ok'
          : '${json['ingest_status'] ?? 'ok'}'.trim(),
      canMergeSupplementary: json['can_merge_supplementary'] == true,
    );
  }

  static String _defaultTag(String docRole) {
    switch (docRole) {
      case 'supplementary':
        return '보충';
      case 'merged':
        return '메인+서플먼터리';
      default:
        return '메인';
    }
  }

  static bool _retentionBool(Object? block, String key) {
    if (block is! Map) return false;
    return block[key] == true;
  }

  static int? _retentionInt(Object? block, String key) {
    if (block is! Map) return null;
    final v = block[key];
    if (v is int) return v;
    if (v is num) return v.toInt();
    return int.tryParse('$v');
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
  final String expiresAt;
  final bool retentionWarn;
  final bool retentionCanExtend;
  final int? retentionDaysUntilExpiry;
  final int retentionExtendDays;
  final String docRole;
  final String libraryTag;
  final String ingestStatus;
  final bool canMergeSupplementary;

  bool get isValid => id.isNotEmpty && title.isNotEmpty;

  String get subtitle {
    final bits = <String>[
      if (libraryTag.isNotEmpty) libraryTag,
      if (sentenceCount > 0) '문장 $sentenceCount',
      if (figureCount > 0) '그림 $figureCount',
      if (stale) '구버전',
      if (retentionWarn && retentionDaysUntilExpiry != null)
        '삭제 ${retentionDaysUntilExpiry!}일 전',
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
