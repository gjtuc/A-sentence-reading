import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/reading_models.dart';

void main() {
  group('ReadingSession cursors', () {
    ReadingSession sample() => ReadingSession(
          sessionId: 'ses_1',
          cacheId: 'c1',
          title: 'T',
          sentences: [
            SentenceView(id: 's1', text: 'one'),
            SentenceView(id: 's2', text: 'two'),
            SentenceView(id: 's3', text: 'three'),
          ],
          figures: [
            FigureView(id: 'f1', imageSrc: 'data:image/png;base64,aaaa'),
            FigureView(id: 'f2', imageSrc: ''),
          ],
          sentenceIndex: 0,
          figureIndex: 0,
        );

    test('advanceSentence leaves figureIndex unchanged', () {
      final s = sample();
      s.advanceSentence(1);
      expect(s.sentenceIndex, 1);
      expect(s.figureIndex, 0);
      s.advanceSentence(1);
      expect(s.sentenceIndex, 2);
      expect(s.figureIndex, 0);
      s.advanceSentence(1);
      expect(s.sentenceIndex, 0);
      expect(s.figureIndex, 0);
    });

    test('advanceFigure leaves sentenceIndex unchanged', () {
      final s = sample();
      s.advanceSentence(2);
      expect(s.sentenceIndex, 2);
      s.advanceFigure(1);
      expect(s.figureIndex, 1);
      expect(s.sentenceIndex, 2);
      s.advanceFigure(1);
      expect(s.figureIndex, 0);
      expect(s.sentenceIndex, 2);
    });

    test('edge empty lists and clamp', () {
      final s = ReadingSession(
        sessionId: 'ses',
        cacheId: '',
        title: '',
        sentences: const [],
        figures: const [],
        sentenceIndex: 99,
        figureIndex: -3,
      );
      expect(s.sentenceIndex, 0);
      expect(s.figureIndex, 0);
      s.advanceSentence(1);
      s.advanceFigure(-1);
      expect(s.sentenceIndex, 0);
      expect(s.figureIndex, 0);
    });

    test('preserveLazyTranslationsFrom keeps KO text on re-open', () {
      final prior = ReadingSession(
        sessionId: 'ses_old',
        cacheId: 'paper1',
        title: 'T',
        sentences: [
          SentenceView(id: 's1', text: 'one', textKo: '하나'),
        ],
        figures: [
          FigureView(id: 'f1', imageSrc: '', captionKo: '그림1'),
        ],
      );
      final next = ReadingSession(
        sessionId: 'ses_new',
        cacheId: 'paper1',
        title: 'T',
        sentences: [SentenceView(id: 's1', text: 'one')],
        figures: [FigureView(id: 'f1', imageSrc: '')],
      );
      next.preserveLazyTranslationsFrom(prior);
      expect(next.sentences[0].textKo, '하나');
      expect(next.figures[0].captionKo, '그림1');
    });

    test('preserveLazyFigureImagesFrom keeps fetched PNGs on re-open', () {
      final prior = ReadingSession(
        sessionId: 'ses_old',
        cacheId: 'paper1',
        title: 'T',
        sentences: [SentenceView(id: 's1', text: 'one')],
        figures: [
          FigureView(id: 'f1', imageSrc: 'data:image/png;base64,aaaa'),
          FigureView(id: 'f2', imageSrc: 'data:image/png;base64,bbbb'),
        ],
      );
      final next = ReadingSession(
        sessionId: 'ses_new',
        cacheId: 'paper1',
        title: 'T',
        sentences: [SentenceView(id: 's1', text: 'one')],
        figures: [
          FigureView(id: 'f1', imageSrc: ''),
          FigureView(id: 'f2', imageSrc: ''),
        ],
      );
      next.preserveLazyFigureImagesFrom(prior);
      expect(next.figures[0].imageSrc, 'data:image/png;base64,aaaa');
      expect(next.figures[1].imageSrc, 'data:image/png;base64,bbbb');
    });

    test('mergeFigureWindow fills by index and id only when src present', () {
      final s = sample();
      s.mergeFigureWindow([
        {'index': 1, 'image_src': 'data:image/png;base64,bbbb'},
        {'index': 0, 'image_src': ''},
      ]);
      expect(s.figures[0].imageSrc, 'data:image/png;base64,aaaa');
      expect(s.figures[1].imageSrc, 'data:image/png;base64,bbbb');
    });

    test('fromOpenJson tolerant garbage', () {
      final s = ReadingSession.fromOpenJson({
        'session_id': 'ses_x',
        'sentences': [
          {'id': 'a', 'text': 'A'},
          'nope',
          {'id': 'b', 'text': 'B'},
        ],
        'figures': [
          null,
          {'id': 'f', 'image_src': 'http://x'},
        ],
        'sentence_index': '1',
        'figure_index': 9,
        'warnings': ['stale_pipeline', ''],
      });
      expect(s.isValid, isTrue);
      expect(s.sentenceCount, 2);
      expect(s.figureCount, 1);
      expect(s.sentenceIndex, 1);
      expect(s.figureIndex, 0);
      expect(s.warnings, ['stale_pipeline']);
    });
  });

  group('decodeRasterDataUrl', () {
    test('edge svg and empty', () {
      expect(decodeRasterDataUrl(null), isNull);
      expect(decodeRasterDataUrl(''), isNull);
      expect(decodeRasterDataUrl('data:image/svg+xml,abc'), isNull);
      expect(decodeRasterDataUrl('not-data'), isNull);
    });

    test('png base64', () {
      const b64 =
          'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';
      final d = decodeRasterDataUrl('data:image/png;base64,$b64');
      expect(d, isNotNull);
      expect(d!.bytes.length, greaterThan(10));
    });
  });
}
