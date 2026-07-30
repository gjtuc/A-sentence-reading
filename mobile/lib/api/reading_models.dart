/// Reading-session shapes from open / session JSON (design/33 · design/63).
///
/// INVARIANT: [ReadingSession.advanceSentence] never touches [figureIndex].
/// INVARIANT: [ReadingSession.advanceFigure] never touches [sentenceIndex].
library;

import 'dart:convert';
import 'dart:typed_data';

/// One sentence row from the session payload.
class SentenceView {
  SentenceView({
    required this.id,
    required this.text,
    this.section = '',
    this.textKo = '',
  });

  factory SentenceView.fromJson(Map<String, dynamic>? json) {
    if (json == null) return SentenceView(id: '', text: '');
    return SentenceView(
      id: '${json['id'] ?? ''}'.trim(),
      text: '${json['text'] ?? ''}',
      section: '${json['section'] ?? ''}'.trim(),
      textKo: '${json['text_ko'] ?? ''}',
    );
  }

  final String id;
  final String text;
  final String section;
  final String textKo;

  bool get hasText => text.trim().isNotEmpty;
}

/// One figure row — [imageSrc] may be data-URL, http(s), or relative path.
class FigureView {
  FigureView({
    required this.id,
    required this.imageSrc,
    this.caption = '',
    this.captionKo = '',
  });

  factory FigureView.fromJson(Map<String, dynamic>? json) {
    if (json == null) return FigureView(id: '', imageSrc: '');
    return FigureView(
      id: '${json['id'] ?? ''}'.trim(),
      imageSrc: '${json['image_src'] ?? ''}'.trim(),
      caption: '${json['caption'] ?? ''}',
      captionKo: '${json['caption_ko'] ?? ''}',
    );
  }

  final String id;
  final String imageSrc;
  final String caption;
  final String captionKo;
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
          if (f.id.isNotEmpty || f.imageSrc.isNotEmpty) figures.add(f);
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
    return ReadingSession(
      sessionId: '${json['session_id'] ?? ''}'.trim(),
      cacheId: '${json['cache_id'] ?? ''}'.trim(),
      title: '${json['title'] ?? fallbackTitle}'.trim(),
      sentences: sentences,
      figures: figures,
      sentenceIndex: asInt(json['sentence_index']),
      figureIndex: asInt(json['figure_index']),
      warnings: warnings,
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

  bool get isValid => sessionId.isNotEmpty;

  int get sentenceCount => sentences.length;
  int get figureCount => figures.length;

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
}
