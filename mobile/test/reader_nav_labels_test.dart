import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/cite_refs.dart';
import 'package:sentence_reading/api/reader_nav_labels.dart';
import 'package:sentence_reading/api/reading_models.dart';

void main() {
  test('stripCiteMarkersForDisplay removes word-attached dollar cite', () {
    expect(
      stripCiteMarkersForDisplay('carbon dioxide\$1.'),
      'carbon dioxide.',
    );
    expect(
      stripCiteMarkersForDisplay('costs \$33.00 each'),
      'costs \$33.00 each',
    );
  });

  test('stripCiteMarkersForDisplay removes hybrid bracket-dollar cite', () {
    expect(
      stripCiteMarkersForDisplay('carbon dioxide [8, 9]\$1'),
      'carbon dioxide',
    );
    expect(
      stripCiteMarkersForDisplay(
        'major scientific study [1–4]\$1',
      ),
      'major scientific study',
    );
    expect(
      stripCiteMarkersForDisplay('word CO<sub>2</sub>\$1 here'),
      'word CO<sub>2</sub> here',
    );
  });

  test('parseCiteNumbers reads dollar cite artifacts', () {
    expect(parseCiteNumbers('dioxide\$1 more'), [1]);
    expect(parseCiteNumbers('x\$^{8,9}\$ y'), [8, 9]);
  });

  test('SectionNavIndex labels within section', () {
    final sentences = [
      SentenceView(id: 'a', text: 'A', section: 'introduction'),
      SentenceView(id: 'b', text: 'B', section: 'introduction'),
      SentenceView(id: 'c', text: 'C', section: 'results'),
    ];
    final nav = SectionNavIndex.fromSentences(sentences);
    expect(nav.labelFor(0), 'Introduction 1 / 2');
    expect(nav.labelFor(1), 'Introduction 2 / 2');
    expect(nav.labelFor(2), 'Results 1 / 1');
  });

  test('SectionNavIndex picker mapping', () {
    final sentences = [
      SentenceView(id: 'a', text: 'A', section: 'introduction'),
      SentenceView(id: 'b', text: 'B', section: 'introduction'),
      SentenceView(id: 'c', text: 'C', section: 'results'),
    ];
    final nav = SectionNavIndex.fromSentences(sentences);
    expect(nav.globalIndexFor(0, 1), 1);
    expect(nav.globalIndexFor(1, 0), 2);
    expect(nav.selectionForGlobal(2), (1, 0));
    final parts = nav.headerPartsFor(1);
    expect(parts.sectionName, 'Introduction');
    expect(parts.rightLabel, '2 / 2');
  });

  test('FigureNavIndex picker mapping', () {
    final figures = [
      FigureView(id: 'f1', imageSrc: '', slotKey: 'fig:1'),
      FigureView(id: 'f2', imageSrc: '', slotKey: 'fig:2'),
      FigureView(id: 't1', imageSrc: '', slotKey: 'table:1'),
    ];
    final nav = FigureNavIndex.fromFigures(figures);
    expect(nav.carouselIndexFor(0, 1), 1);
    expect(nav.carouselIndexFor(1, 0), 2);
    expect(nav.selectionForCarousel(2), (1, 0));
    expect(nav.headerPartsFor(1).rightLabel, '2 / 2');
  });

  test('FigureNavIndex title page cover', () {
    final figures = [
      FigureView(id: 'cover', imageSrc: '', caption: 'Title page (p.1)'),
      FigureView(id: 'f1', imageSrc: '', slotKey: 'fig:1'),
      FigureView(id: 'f2', imageSrc: '', slotKey: 'fig:2'),
    ];
    final nav = FigureNavIndex.fromFigures(figures);
    expect(nav.kindCount, 2);
    expect(nav.kindLabelAt(0), 'Title Page');
    expect(nav.labelFor(0), 'title page 1 / 1');
    expect(nav.headerPartsFor(1).rightLabel, '1 / 2');
    expect(nav.figureBookmarkKeyForCarousel(0), 'title_page:1');
    expect(countLibraryFigures(figures), 2);
  });

  test('FigureNavIndex supplementary slot keys', () {
    final figures = [
      FigureView(id: 'f1', imageSrc: '', slotKey: 'fig:1'),
      FigureView(id: 'fs', imageSrc: '', slotKey: 'fig:s2'),
    ];
    final nav = FigureNavIndex.fromFigures(figures);
    expect(nav.kindCount, 2);
    expect(nav.carouselIndexFor(1, 0), 1);
    expect(nav.headerPartsFor(1).rightLabel, 'S2 / S2');
  });
}
