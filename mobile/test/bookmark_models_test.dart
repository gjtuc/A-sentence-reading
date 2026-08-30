import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/bookmark_gate.dart';
import 'package:sentence_reading/api/bookmark_models.dart';
import 'package:sentence_reading/api/reader_nav_labels.dart';
import 'package:sentence_reading/api/reading_models.dart';

void main() {
  test('sentence bookmark key from section position', () {
    final nav = SectionNavIndex.fromSentences([
      SentenceView(id: 's1', text: 'a', section: 'introduction'),
      SentenceView(id: 's2', text: 'b', section: 'introduction'),
      SentenceView(id: 's3', text: 'c', section: 'results'),
    ]);
    expect(nav.sentenceBookmarkKeyForGlobal(1), 'introduction:2');
    expect(nav.sentenceBookmarkKeyForSelection(0, 0), 'introduction:1');
    expect(nav.isValidSentenceBookmarkKey('introduction:2'), isTrue);
    expect(nav.isValidSentenceBookmarkKey('introduction:9'), isFalse);
  });

  test('figure bookmark key includes supplementary kinds', () {
    final nav = FigureNavIndex.fromFigures([
      FigureView(
        id: 'f1',
        slotKey: 'fig:1',
        caption: 'Figure 1',
        imageSrc: '',
      ),
      FigureView(
        id: 'f2',
        slotKey: 'fig:s2',
        caption: 'Figure S2',
        imageSrc: '',
      ),
    ]);
    expect(nav.figureBookmarkKeyForCarousel(0), 'figure:1');
    expect(nav.figureBookmarkKeyForCarousel(1), 'figure_s:2');
    expect(nav.isValidFigureBookmarkKey('figure_s:2'), isTrue);
  });

  test('merge bookmarks latest at wins delete', () {
    final a = PaperBookmarks(
      sentences: {
        'introduction:1': BookmarkEvent(at: '2026-01-01T00:00:00Z'),
      },
    );
    final b = PaperBookmarks(
      sentences: {
        'introduction:1': BookmarkEvent(at: '2026-01-02T00:00:00Z', deleted: true),
      },
    );
    final merged = mergePaperBookmarks(a, b);
    expect(merged.activeSentenceKeys, isEmpty);
  });

  test('prune removes stale keys after reanalyze', () {
    final nav = SectionNavIndex.fromSentences([
      SentenceView(id: 's1', text: 'a', section: 'introduction'),
    ]);
    final figNav = FigureNavIndex.fromFigures(const []);
    final paper = PaperBookmarks(
      sentences: {
        'introduction:99': BookmarkEvent(at: 't'),
        'introduction:1': BookmarkEvent(at: 't'),
      },
    );
    final pruned = prunePaperBookmarks(
      paper: paper,
      sectionNav: nav,
      figureNav: figNav,
    );
    expect(pruned.activeSentenceKeys, {'introduction:1'});
  });

  test('totalActiveCount sums sentence and figure bookmarks', () {
    final paper = PaperBookmarks(
      sentences: {
        'introduction:1': BookmarkEvent(at: 't'),
        'introduction:2': BookmarkEvent(at: 't'),
      },
      figures: {
        'figure:1': BookmarkEvent(at: 't'),
      },
    );
    expect(paper.totalActiveCount, 3);
    expect(const PaperBookmarks().totalActiveCount, 0);
  });
}
