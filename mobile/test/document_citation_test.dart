import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/document_citation.dart';
import 'package:sentence_reading/api/reading_models.dart';

ReadingSession _session({
  List<SentenceView> sentences = const [],
  DocumentCitation documentCitation = const DocumentCitation(),
  String title = '',
}) {
  return ReadingSession(
    sessionId: 's1',
    cacheId: 'c1',
    title: title,
    sentences: sentences,
    figures: const [],
    documentCitation: documentCitation,
  );
}

void main() {
  test('parseDocumentCitation empty and valid', () {
    expect(parseDocumentCitation(null), const DocumentCitation());
    expect(parseDocumentCitation({'text': 'ab'}), const DocumentCitation());
    final c = parseDocumentCitation({
      'text': 'Hello World Paper Title',
      'doi': '10.1/abc',
    });
    expect(c.isVisible, isTrue);
    expect(c.doi, '10.1/abc');
  });

  test('extractDoiFromText', () {
    expect(
      extractDoiFromText('see https://doi.org/10.1000/xyz'),
      '10.1000/xyz',
    );
    expect(
      extractDoiFromText('doi:10.1000/xyz).'),
      '10.1000/xyz',
    );
  });

  test('effectiveCitation uses server field first', () {
    final s = _session(
      documentCitation: const DocumentCitation(
        text: 'Server row',
        doi: '10.1/srv',
      ),
    );
    expect(effectiveCitation(s).text, 'Server row');
  });

  test('effectiveCitation fallback from title section', () {
    final s = _session(
      title: 'Nickel Catalysts for Dry Reforming of Methane',
      sentences: [
        SentenceView(
          id: '1',
          text: 'Nickel Catalysts for Dry Reforming of Methane',
          section: 'title',
        ),
        SentenceView(
          id: '2',
          text: 'doi:10.1016/j.jcat.2019.01.001',
          section: 'title',
        ),
      ],
    );
    final c = effectiveCitation(s);
    expect(c.doi, startsWith('10.1016/'));
    expect(c.source, 'client_fallback');
  });

  test('shouldShowThisPaperPanel only title position 1', () {
    final s = _session(
      title: 'Long Enough Paper Title Here',
      documentCitation: const DocumentCitation(text: 'Long Enough Paper Title Here'),
      sentences: [
        SentenceView(id: '1', text: 'Long Enough Paper Title Here', section: 'title'),
        SentenceView(id: '2', text: 'Author line', section: 'title'),
        SentenceView(id: '3', text: 'Abstract text here.', section: 'abstract'),
      ],
    );
    s.sentenceIndex = 0;
    expect(
      shouldShowThisPaperPanel(
        session: s,
        citePanelEnabled: true,
        citePanelServerAvailable: true,
        thisPaperServerAvailable: true,
      ),
      isTrue,
    );
    s.sentenceIndex = 1;
    expect(
      shouldShowThisPaperPanel(
        session: s,
        citePanelEnabled: true,
        citePanelServerAvailable: true,
        thisPaperServerAvailable: true,
      ),
      isFalse,
    );
    s.sentenceIndex = 2;
    expect(
      shouldShowThisPaperPanel(
        session: s,
        citePanelEnabled: true,
        citePanelServerAvailable: true,
        thisPaperServerAvailable: true,
      ),
      isFalse,
    );
  });

  test('shouldShowThisPaperPanel respects cite kill', () {
    final s = _session(
      title: 'Long Enough Paper Title Here',
      documentCitation: const DocumentCitation(text: 'Long Enough Paper Title Here'),
      sentences: [
        SentenceView(id: '1', text: 'Long Enough Paper Title Here', section: 'title'),
      ],
    );
    expect(
      shouldShowThisPaperPanel(
        session: s,
        citePanelEnabled: false,
        citePanelServerAvailable: true,
        thisPaperServerAvailable: true,
      ),
      isFalse,
    );
  });
}
