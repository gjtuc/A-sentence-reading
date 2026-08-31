/// Reading-session shapes from open / session JSON (design/33 · design/63).
///
/// INVARIANT: [ReadingSession.advanceSentence] never touches [figureIndex].
/// INVARIANT: [ReadingSession.advanceFigure] never touches [sentenceIndex].
library;

import 'dart:convert';
import 'dart:typed_data';

import 'cite_refs.dart';
import 'document_citation.dart';
import 'reader_nav_labels.dart';

/// Ingest quality metrics persisted in session.json (design/167).
class IngestQuality {
  const IngestQuality({
    this.coverageRatio = 1.0,
    this.bodyRatio = 0.0,
    this.ungroundedCount = 0,
    this.chunksFallbackSplit = const [],
    this.chunksOk = 0,
    this.chunksTotal = 0,
  });

  factory IngestQuality.fromJson(Object? raw) {
    if (raw is! Map) return const IngestQuality();
    double asDouble(Object? v, [double d = 0]) {
      if (v is num) return v.toDouble();
      return double.tryParse('$v') ?? d;
    }
    int asInt(Object? v, [int d = 0]) {
      if (v is int) return v;
      if (v is num) return v.toInt();
      return int.tryParse('$v') ?? d;
    }
    final fallback = <int>[];
    final fb = raw['chunks_fallback_split'];
    if (fb is List) {
      for (final x in fb) {
        if (x is int) {
          fallback.add(x);
        } else if (x is num) {
          fallback.add(x.toInt());
        }
      }
    }
    return IngestQuality(
      coverageRatio: asDouble(raw['coverage_ratio'], 1.0),
      bodyRatio: asDouble(raw['body_ratio']),
      ungroundedCount: asInt(raw['ungrounded_count']),
      chunksFallbackSplit: fallback,
      chunksOk: asInt(raw['chunks_ok']),
      chunksTotal: asInt(raw['chunks_total']),
    );
  }

  final double coverageRatio;
  final double bodyRatio;
  final int ungroundedCount;
  final List<int> chunksFallbackSplit;
  final int chunksOk;
  final int chunksTotal;

  bool needsBanner(List<String> warnings) {
    if (warnings.any((w) =>
        w.startsWith('coverage_') ||
        w.startsWith('partial_debone') ||
        w.startsWith('chunk_fallback_split') ||
        w.startsWith('ungrounded_sentences') ||
        w.startsWith('high_body_ratio'))) {
      return true;
    }
    return coverageRatio < 0.65 || ungroundedCount > 0;
  }
}

/// One sentence row from the session payload.
class SentenceView {
  SentenceView({
    required this.id,
    required this.text,
    this.section = '',
    this.textKo = '',
    this.qualityFlags = const [],
  });

  factory SentenceView.fromJson(Map<String, dynamic>? json) {
    if (json == null) return SentenceView(id: '', text: '');
    final flags = <String>[];
    final rawF = json['quality_flags'];
    if (rawF is List) {
      for (final f in rawF) {
        final s = '$f'.trim();
        if (s.isNotEmpty) flags.add(s);
      }
    }
    return SentenceView(
      id: '${json['id'] ?? ''}'.trim(),
      text: '${json['text'] ?? ''}',
      section: '${json['section'] ?? ''}'.trim(),
      textKo: '${json['text_ko'] ?? ''}',
      qualityFlags: flags,
    );
  }

  final String id;
  final String text;
  final String section;
  final String textKo;
  final List<String> qualityFlags;

  bool get hasText => text.trim().isNotEmpty;
  bool get isUngrounded => qualityFlags.contains('ungrounded');
}

/// One figure row — [imageSrc] may be data-URL, http(s), relative, or empty stub.
class FigureView {
  FigureView({
    required this.id,
    required this.imageSrc,
    this.caption = '',
    this.captionKo = '',
    this.slotKey = '',
  });

  factory FigureView.fromJson(Map<String, dynamic>? json) {
    if (json == null) return FigureView(id: '', imageSrc: '');
    return FigureView(
      id: '${json['id'] ?? ''}'.trim(),
      imageSrc: '${json['image_src'] ?? ''}'.trim(),
      caption: '${json['caption'] ?? ''}',
      captionKo: '${json['caption_ko'] ?? ''}',
      slotKey: '${json['slot_key'] ?? ''}'.trim(),
    );
  }

  final String id;
  /// design/129 — mutable so ±1 window can fill stubs without rebuilding the list.
  String imageSrc;
  final String caption;
  final String captionKo;
  /// design/151 — fig:3 / table:2 for carousel label (not raw carousel index).
  final String slotKey;
}

/// Decoded raster bytes for Flutter [Image.memory], if applicable.
class DecodedImageBytes {
  DecodedImageBytes(this.bytes, {this.mime = 'image/png'});

  final Uint8List bytes;
  final String mime;
}

/// Parse `data:image/...;base64,...` (PNG/JPEG). SVG / other → null (show placeholder).
DecodedImageBytes? decodeRasterDataUrl(String? src) {
  if (src == null) return null;
  final s = src.trim();
  if (!s.startsWith('data:image/')) return null;
  // EDGE: svg data URLs are not decoded here (no flutter_svg in MVP).
  if (s.startsWith('data:image/svg')) return null;
  final comma = s.indexOf(',');
  if (comma < 0) return null;
  final meta = s.substring(0, comma).toLowerCase();
  final payload = s.substring(comma + 1);
  if (!meta.contains(';base64')) return null;
  try {
    final bytes = base64Decode(payload);
    if (bytes.isEmpty) return null;
    final mime = meta.startsWith('data:')
        ? meta.substring(5).split(';').first
        : 'image/png';
    return DecodedImageBytes(Uint8List.fromList(bytes), mime: mime);
  } catch (_) {
    // EDGE: corrupt base64
    return null;
  }
}

/// Full opened paper with independent cursors.
class ReadingSession {
  ReadingSession({
    required this.sessionId,
    required this.cacheId,
    required this.title,
    required this.sentences,
    required this.figures,
    this.sentenceIndex = 0,
    this.figureIndex = 0,
    this.warnings = const [],
    this.ingestQuality,
    this.references = const [],
    this.documentCitation = const DocumentCitation(),
    this.supplementaryMerged = false,
    this.translatePending = false,
  }) {
    clampIndices();
  }

  factory ReadingSession.fromOpenJson(
    Map<String, dynamic> json, {
    String fallbackTitle = '',
  }) {
    int asInt(Object? v, [int d = 0]) {
      if (v is int) return v;
      if (v is num) return v.toInt();
      return int.tryParse('$v') ?? d;
    }

    final sentences = <SentenceView>[];
    final rawS = json['sentences'];
    if (rawS is List) {
      for (final item in rawS) {
        if (item is Map) {
          final s = SentenceView.fromJson(Map<String, dynamic>.from(item));
          if (s.id.isNotEmpty || s.hasText) sentences.add(s);
        }
      }
    }
    final figures = <FigureView>[];
    final rawF = json['figures'];
    if (rawF is List) {
      for (final item in rawF) {
        if (item is Map) {
          final f = FigureView.fromJson(Map<String, dynamic>.from(item));
          // design/129 — keep caption stubs with empty image_src (lazy fill).
          if (f.id.isNotEmpty || f.imageSrc.isNotEmpty || f.caption.trim().isNotEmpty) {
            figures.add(f);
          }
        }
      }
    }
    final warnings = <String>[];
    final rawW = json['warnings'];
    if (rawW is List) {
      for (final w in rawW) {
        final s = '$w'.trim();
        if (s.isNotEmpty) warnings.add(s);
      }
    }
    final iqRaw = json['ingest_quality'];
    final ingestQuality =
        iqRaw is Map ? IngestQuality.fromJson(Map<String, dynamic>.from(iqRaw)) : null;
    return ReadingSession(
      sessionId: '${json['session_id'] ?? ''}'.trim(),
      cacheId: '${json['cache_id'] ?? ''}'.trim(),
      title: '${json['title'] ?? fallbackTitle}'.trim(),
      sentences: sentences,
      figures: figures,
      sentenceIndex: asInt(json['sentence_index']),
      figureIndex: asInt(json['figure_index']),
      warnings: warnings,
      ingestQuality: ingestQuality,
      references: parseReferenceList(json['references']),
      documentCitation: parseDocumentCitation(json['document_citation']),
      supplementaryMerged: json['supplementary_merged'] == true,
      translatePending: json['translate_pending'] == true,
    );
  }

  final String sessionId;
  final String cacheId;
  String title;
  final List<SentenceView> sentences;
  final List<FigureView> figures;
  int sentenceIndex;
  int figureIndex;
  final List<String> warnings;
  final IngestQuality? ingestQuality;
  /// design/148 — bibliography rows from ingest (cite panel).
  final List<CiteRefEntry> references;
  /// design/157 — this paper bibliographic row (Title panel).
  final DocumentCitation documentCitation;
  /// design/152 — merged main+SI enables bare S2 fig chips.
  final bool supplementaryMerged;
  /// design/99+129 — server is backfilling KO after /open.
  final bool translatePending;

  bool get hasAnyTranslation {
    for (final s in sentences) {
      if (s.hasText && s.textKo.trim().isNotEmpty) return true;
    }
    return false;
  }

  bool get isValid => sessionId.isNotEmpty;

  int get sentenceCount => sentences.length;
  int get figureCount => figures.length;

  SectionNavIndex get sectionNav => SectionNavIndex.fromSentences(sentences);
  FigureNavIndex get figureNav => FigureNavIndex.fromFigures(figures);

  SentenceView? get currentSentence {
    if (sentences.isEmpty) return null;
    return sentences[sentenceIndex];
  }

  FigureView? get currentFigure {
    if (figures.isEmpty) return null;
    return figures[figureIndex];
  }

  void clampIndices() {
    if (sentences.isEmpty) {
      sentenceIndex = 0;
    } else {
      sentenceIndex = sentenceIndex.clamp(0, sentences.length - 1);
    }
    if (figures.isEmpty) {
      figureIndex = 0;
    } else {
      figureIndex = figureIndex.clamp(0, figures.length - 1);
    }
  }

  /// INVARIANT: does not modify [figureIndex].
  void advanceSentence(int delta) {
    if (sentences.isEmpty) return;
    final n = sentences.length;
    sentenceIndex = (sentenceIndex + delta) % n;
    if (sentenceIndex < 0) sentenceIndex += n;
  }

  /// INVARIANT: does not modify [sentenceIndex].
  void advanceFigure(int delta) {
    if (figures.isEmpty) return;
    final n = figures.length;
    figureIndex = (figureIndex + delta) % n;
    if (figureIndex < 0) figureIndex += n;
  }

  /// design/129 — merge `/figures/window` rows into stubs by index (or id).
  void mergeFigureWindow(List<Map<String, dynamic>> rows) {
    for (final row in rows) {
      final src = '${row['image_src'] ?? ''}'.trim();
      if (src.isEmpty) continue;
      final idxRaw = row['index'];
      final idx = idxRaw is int
          ? idxRaw
          : (idxRaw is num ? idxRaw.toInt() : int.tryParse('$idxRaw'));
      if (idx != null && idx >= 0 && idx < figures.length) {
        figures[idx].imageSrc = src;
        continue;
      }
      final id = '${row['id'] ?? ''}'.trim();
      if (id.isEmpty) continue;
      for (final f in figures) {
        if (f.id == id) {
          f.imageSrc = src;
          break;
        }
      }
    }
  }
}
