/// Paper library JSON shapes from `/api/cache/papers*` (design/18 · design/62 · 152).
library;

import 'doc_parts.dart';

/// design/489 - paper | review | general; anything else reads as a paper.
String normalizeDocKind(Object? raw) {
  final v = '${raw ?? ''}'.trim().toLowerCase();
  return (v == 'review' || v == 'general') ? v : 'paper';
}

/// design/489 - card tag for a main-role upload that is not a paper.
String docKindLibraryTag(Object? kind) {
  switch (normalizeDocKind(kind)) {
    case 'review':
      return '심사 기록';
    case 'general':
      return '일반 글';
    default:
      return '';
  }
}

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
    this.docRole = 'main',
    this.libraryTag = '',
    this.ingestStatus = 'ok',
    this.canMergeSupplementary = false,
    this.pairedCacheId = '',
    this.harmonizePending = false,
    this.harmonizeTotal = 0,
    this.harmonizeDone = 0,
    this.harmonizeFailed = 0,
    this.harmonizeAttemptN = 0,
    this.contentHash = '',
    this.docKind = 'paper',
    this.displayTitle = '',
    this.labelKind = '',
    this.sourceName = '',
    this.mergedSections = const [],
    this.mergePartIds = const [],
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
    final docKind = normalizeDocKind(json['doc_kind']);
    final sectionsRaw = json['merged_sections'];
    final mergedSections = <String>[
      if (sectionsRaw is List)
        for (final s in sectionsRaw) normalizePartSection(s),
    ];
    var libraryTag = '${json['library_tag'] ?? ''}'.trim();
    if (libraryTag.isEmpty) {
      libraryTag = _defaultTag(docRole, docKind, mergedSections);
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
      docRole: docRole,
      libraryTag: libraryTag,
      ingestStatus: '${json['ingest_status'] ?? 'ok'}'.trim().isEmpty
          ? 'ok'
          : '${json['ingest_status'] ?? 'ok'}'.trim(),
      canMergeSupplementary: json['can_merge_supplementary'] == true,
      pairedCacheId: '${json['paired_cache_id'] ?? ''}'.trim(),
      harmonizePending: json['harmonize_pending'] == true,
      harmonizeTotal: asInt(json['harmonize_total']),
      harmonizeDone: asInt(json['harmonize_done']),
      harmonizeFailed: asInt(json['harmonize_failed']),
      harmonizeAttemptN: asInt(json['harmonize_attempt_n']),
      contentHash: '${json['content_hash'] ?? ''}'.trim().toLowerCase(),
      docKind: docKind,
      sourceName: cleanSourceName(json['source_name']),
      mergedSections: mergedSections,
    );
  }

  static String _defaultTag(
    String docRole, [
    String docKind = 'paper',
    List<String> mergedSections = const [],
  ]) {
    final kindTag = docKindLibraryTag(docKind);
    if (docRole == 'main' && kindTag.isNotEmpty) return kindTag;
    switch (docRole) {
      case 'supplementary':
        return '보충';
      case 'merged':
        return mergedTagFor(mergedSections);
      default:
        return '메인';
    }
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
  final String docRole;
  final String libraryTag;
  final String ingestStatus;
  final bool canMergeSupplementary;

  /// design/240 — mate cache id from soft pairing (empty if none).
  final String pairedCacheId;

  /// design/169o — server residual 재감수 still running after ingest done.
  final bool harmonizePending;
  final int harmonizeTotal;
  final int harmonizeDone;
  final int harmonizeFailed;
  final int harmonizeAttemptN;

  /// design/222 — SHA-256 of source PDF when known (picker/library join).
  final String contentHash;

  /// design/489 - paper | review | general; only a paper pairs with SI.
  final String docKind;

  /// design/490 - the reader's own title and kind (empty = as analysed). [title]
  /// stays the analysed one, which pairing and duplicate checks use.
  final String displayTitle;
  final String labelKind;

  /// design/492 — the upload's file name ('' for papers analysed before it was kept).
  final String sourceName;

  /// design/492 — what is attached behind a merged paper, in reading order.
  final List<String> mergedSections;

  /// design/492 — ids this paper's merge button takes in (set by the library
  /// pass, never by the server).
  final List<String> mergePartIds;

  String get shownTitle => displayTitle.isNotEmpty ? displayTitle : title;

  String get effectiveKind => labelKind.isNotEmpty ? labelKind : docKind;

  /// The card tag, with the reader's kind over the analysed one.
  String get shownTag {
    if (labelKind.isEmpty || pairedCacheId.trim().isNotEmpty) return libraryTag;
    final kindTag = docKindLibraryTag(labelKind);
    if (kindTag.isNotEmpty) return kindTag;
    return docRole == 'main' ? '메인' : libraryTag;
  }

  bool get isValid => id.isNotEmpty && title.isNotEmpty;

  /// design/261 — mutate pairing / set-row fields without losing the rest.
  PaperEntry copyWith({
    String? pairedCacheId,
    bool? canMergeSupplementary,
    String? libraryTag,
    String? docRole,
    String? ingestStatus,
    int? sentenceCount,
    int? figureCount,
    String? displayTitle,
    String? labelKind,
    List<String>? mergePartIds,
  }) {
    return PaperEntry(
      id: id,
      title: title,
      source: source,
      updatedAt: updatedAt,
      sentenceCount: sentenceCount ?? this.sentenceCount,
      figureCount: figureCount ?? this.figureCount,
      debone: debone,
      pipelineVersion: pipelineVersion,
      stale: stale,
      hasSource: hasSource,
      docRole: docRole ?? this.docRole,
      libraryTag: libraryTag ?? this.libraryTag,
      ingestStatus: ingestStatus ?? this.ingestStatus,
      canMergeSupplementary:
          canMergeSupplementary ?? this.canMergeSupplementary,
      pairedCacheId: pairedCacheId ?? this.pairedCacheId,
      harmonizePending: harmonizePending,
      harmonizeTotal: harmonizeTotal,
      harmonizeDone: harmonizeDone,
      harmonizeFailed: harmonizeFailed,
      harmonizeAttemptN: harmonizeAttemptN,
      contentHash: contentHash,
      docKind: docKind,
      displayTitle: displayTitle ?? this.displayTitle,
      labelKind: labelKind ?? this.labelKind,
      sourceName: sourceName,
      mergedSections: mergedSections,
      mergePartIds: mergePartIds ?? this.mergePartIds,
    );
  }

  /// design/160 — sentence + figure counts only (no library tag / stale / TTL text).
  /// design/196 — totals + optional resume section in one line.
  /// design/218 — prefix libraryTag so main/SI role is visible in subtitle too.
  String metaResumeLine({String? resumeSection}) {
    final meta = metaLine();
    String body;
    if (resumeSection == null) {
      body = meta;
    } else {
      final section = resumeSection.trim();
      if (section.isEmpty) {
        body = meta.isEmpty ? "읽는 중" : "$meta 읽는 중";
      } else if (meta.isEmpty) {
        body = "$section 읽는 중";
      } else {
        body = "$meta · $section 읽는 중";
      }
    }
    final tag = libraryTag.trim();
    if (tag.isNotEmpty && tag != '로컬') {
      return body.isEmpty ? tag : "$tag · $body";
    }
    return body;
  }

  /// Formats reading and practice progress on a dedicated line.
  /// e.g. "Introduction 22 / 28 읽는 중 · Introduction 3 / 28 연습 중"
  String progressResumeLine({
    String? readSection,
    String? practiceSection,
  }) {
    final bits = <String>[];
    final r = (readSection ?? '').trim();
    if (r.isNotEmpty) bits.add('$r 읽는 중');
    final p = (practiceSection ?? '').trim();
    if (p.isNotEmpty) bits.add('$p 연습 중');
    return bits.join(' · ');
  }

  String metaLine({int? figureCountOverride}) {
    final fc = figureCountOverride ?? figureCount;
    final bits = <String>[
      if (sentenceCount > 0) '문장 $sentenceCount',
      if (fc > 0) '그림 $fc',
    ];
    return bits.join(' · ');
  }

  /// design/160 — 보관 / 읽기 timestamps (local `M/d HH:mm`). design/494 — no expiry:
  /// a paper on the device is never deleted by a timer.
  String timingLine({String lastReadLeftAt = ''}) {
    final bits = <String>[];
    if (updatedAt.isNotEmpty) {
      final stored = formatPaperMetaDateTime(updatedAt);
      if (stored.isNotEmpty) {
        bits.add('보관: $stored');
      }
    }
    if (lastReadLeftAt.isNotEmpty) {
      final read = formatPaperMetaDateTime(lastReadLeftAt);
      if (read.isNotEmpty) bits.add('읽기: $read');
    }
    return bits.join('  ');
  }

  /// Legacy subtitle — tests only; library UI uses [metaLine] + [timingLine].
  String get subtitle {
    final bits = <String>[
      if (libraryTag.isNotEmpty) libraryTag,
      if (sentenceCount > 0) '문장 $sentenceCount',
      if (figureCount > 0) '그림 $figureCount',
      if (stale) '구버전',
    ];
    return bits.join(' · ');
  }
}

/// ISO UTC → local `M/d` for library expiry suffix only.
String formatPaperMetaDate(String iso) {
  final raw = iso.trim();
  if (raw.isEmpty) return '';
  final dt = DateTime.tryParse(raw);
  if (dt == null) return '';
  final local = dt.toLocal();
  return '${local.month}/${local.day}';
}

/// ISO UTC → local `M/d HH:mm` for library meta lines.
String formatPaperMetaDateTime(String iso) {
  final raw = iso.trim();
  if (raw.isEmpty) return '';
  final dt = DateTime.tryParse(raw);
  if (dt == null) return '';
  final local = dt.toLocal();
  final h = local.hour.toString().padLeft(2, '0');
  final m = local.minute.toString().padLeft(2, '0');
  return '${local.month}/${local.day} $h:$m';
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
