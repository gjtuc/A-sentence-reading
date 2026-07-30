import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/paper_models.dart';

void main() {
  group('PaperEntry', () {
    test('happy path', () {
      final e = PaperEntry.fromJson({
        'id': 'c1',
        'title': 'Hello',
        'source': 'pdf',
        'sentence_count': 12,
        'figure_count': 3,
        'updated_at': '2026-01-01',
        'stale': true,
      });
      expect(e.isValid, isTrue);
      expect(e.subtitle, contains('문장 12'));
      expect(e.subtitle, contains('구버전'));
    });

    test('edge null garbage missing fields', () {
      expect(PaperEntry.fromJson(null).isValid, isFalse);
      expect(PaperEntry.fromJson({}).isValid, isFalse);
      expect(PaperEntry.fromJson({'id': 'x'}).isValid, isFalse);
      expect(PaperEntry.fromJson({'title': 't'}).isValid, isFalse);
      final e = PaperEntry.fromJson({
        'id': '1',
        'title': 'T',
        'sentence_count': 'not-a-number',
        'figure_count': 2.9,
      });
      expect(e.sentenceCount, 0);
      expect(e.figureCount, 2);
    });
  });

  group('OpenedPaper', () {
    test('from open payload', () {
      final o = OpenedPaper.fromOpenJson({
        'session_id': 'ses_1',
        'cache_id': 'c1',
        'title': 'Paper',
        'sentences': [{}, {}],
        'figures': [{}],
        'warnings': ['stale_pipeline', ''],
      });
      expect(o.isValid, isTrue);
      expect(o.sentenceCount, 2);
      expect(o.figureCount, 1);
      expect(o.warnings, ['stale_pipeline']);
    });

    test('edge empty session', () {
      final o = OpenedPaper.fromOpenJson({}, fallbackTitle: 'X');
      expect(o.isValid, isFalse);
      expect(o.title, 'X');
    });
  });
}
