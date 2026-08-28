/// design/157 — this paper row for Title section panel.
library;

import 'reading_models.dart';

final _doi = RegExp(
  r'\b(?:doi[:\s]*)?(10\.\d{4,9}/[-._;()/:A-Z0-9]+)\b',
  caseSensitive: false,
);

class DocumentCitation {
  const DocumentCitation({
    this.text = '',
    this.doi = '',
    this.source = '',
    this.confidence = '',
  });

  final String text;
  final String doi;
  final String source;
  final String confidence;

  bool get isVisible => text.trim().length >= 3;
}

DocumentCitation parseDocumentCitation(Object? raw) {
  if (raw is! Map) return const DocumentCitation();
  final map = Map<String, dynamic>.from(raw);
  final text = '${map['text'] ?? ''}'.trim();
  if (text.length < 3) return const DocumentCitation();
  return DocumentCitation(
    text: text.length > 2000 ? text.substring(0, 2000) : text,
    doi: '${map['doi'] ?? ''}'.trim(),
    source: '${map['source'] ?? ''}'.trim(),
    confidence: '${map['confidence'] ?? ''}'.trim(),
  );
}

String? extractDoiFromText(String? text) {
  final m = _doi.firstMatch(text ?? '');
  if (m == null) return null;
  return m.group(1)!.replaceAll(RegExp(r'[).,;]+$'), '');
}

DocumentCitation effectiveCitation(ReadingSession session) {
  if (session.documentCitation.isVisible) {
    return session.documentCitation;
  }
  final titleSents = session.sentences
      .where((s) => (s.section ?? '').trim().toLowerCase() == 'title')
      .map((s) => s.text)
      .where((t) => t.trim().isNotEmpty);
  final titleBlob = titleSents.join('\n');
  final doi = extractDoiFromText(titleBlob);
  if (doi != null) {
    final title = session.title.trim();
    return DocumentCitation(
      text: title.isNotEmpty ? title : titleBlob.trim(),
      doi: doi,
      source: 'client_fallback',
    );
  }
  final title = session.title.trim();
  if (title.length >= 10) {
    return DocumentCitation(text: title, source: 'title_only');
  }
  return const DocumentCitation();
}

bool shouldShowThisPaperPanel({
  required ReadingSession session,
  required bool citePanelEnabled,
  required bool citePanelServerAvailable,
  required bool thisPaperServerAvailable,
}) {
  if (!citePanelEnabled || !citePanelServerAvailable || !thisPaperServerAvailable) {
    return false;
  }
  if (!effectiveCitation(session).isVisible) return false;
  if (session.sentenceCount == 0) return false;
  final nav = session.sectionNav;
  final (sectionIndex, _) = nav.selectionForGlobal(session.sentenceIndex);
  if (nav.sectionKeyAt(sectionIndex) != 'title') return false;
  final parts = nav.headerPartsFor(session.sentenceIndex);
  return parts.position == 1;
}
