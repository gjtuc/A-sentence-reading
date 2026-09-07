import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/reader_layout_policy.dart';
import 'package:sentence_reading/api/reading_models.dart';

void main() {
  group('firstFigTableChipSentenceIndex', () {
    test('finds first matched chip', () {
      final sentences = [
        SentenceView(id: '0', text: 'Intro [1] only.'),
        SentenceView(id: '1', text: 'See Fig. 1 now.'),
        SentenceView(id: '2', text: 'Table 2 also.'),
      ];
      final figures = [
        FigureView(id: 'f0', imageSrc: '', caption: 'Fig. 1 — XRD'),
        FigureView(id: 'f1', imageSrc: '', caption: 'Table 2 — data'),
      ];
      expect(
        firstFigTableChipSentenceIndex(
          sentences: sentences,
          figures: figures,
        ),
        1,
      );
    });

    test('unmatched fig ignored', () {
      final sentences = [
        SentenceView(id: '0', text: 'Fig. 99 missing.'),
        SentenceView(id: '1', text: 'Fig. 1 present.'),
      ];
      final figures = [FigureView(id: 'f0', imageSrc: '', caption: 'Fig. 1 — ok')];
      expect(
        firstFigTableChipSentenceIndex(
          sentences: sentences,
          figures: figures,
        ),
        1,
      );
    });

    test('null when no chips', () {
      expect(
        firstFigTableChipSentenceIndex(
          sentences: [SentenceView(id: '0', text: 'No figs.')],
          figures: [FigureView(id: 'f0', imageSrc: '', caption: 'Fig. 1 — later')],
        ),
        isNull,
      );
    });
  });

  group('ReaderLayoutPolicy', () {
    test('desire matrix', () {
      final p = ReaderLayoutPolicy()..threshold = 5;
      expect(
        p.desireFor(
          sentenceIndex: 2,
          sectionIsTitle: false,
          hasCover: false,
        ),
        ReaderLayoutDesire.sentenceOnly,
      );
      expect(
        p.desireFor(
          sentenceIndex: 5,
          sectionIsTitle: false,
          hasCover: false,
        ),
        ReaderLayoutDesire.splitDefault,
      );
      expect(
        p.desireFor(
          sentenceIndex: 0,
          sectionIsTitle: true,
          hasCover: true,
        ),
        ReaderLayoutDesire.splitDefault,
      );
      expect(
        p.desireFor(
          sentenceIndex: 0,
          sectionIsTitle: true,
          hasCover: false,
        ),
        ReaderLayoutDesire.sentenceOnly,
      );
    });

    test('pin blocks followsAuto', () {
      final p = ReaderLayoutPolicy()
        ..threshold = 3
        ..pin();
      expect(p.followsAuto, isFalse);
    });
  });
}
