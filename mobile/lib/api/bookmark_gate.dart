/// Validate bookmark keys against current session nav indices (fail-closed prune).
library;

import 'bookmark_models.dart';
import 'reader_nav_labels.dart';

PaperBookmarks prunePaperBookmarks({
  required PaperBookmarks paper,
  required SectionNavIndex sectionNav,
  required FigureNavIndex figureNav,
}) {
  final sentences = <String, BookmarkEvent>{};
  for (final entry in paper.sentences.entries) {
    if (!entry.value.deleted &&
        sectionNav.isValidSentenceBookmarkKey(entry.key)) {
      sentences[entry.key] = entry.value;
    }
  }
  final figures = <String, BookmarkEvent>{};
  for (final entry in paper.figures.entries) {
    if (!entry.value.deleted && figureNav.isValidFigureBookmarkKey(entry.key)) {
      figures[entry.key] = entry.value;
    }
  }
  return PaperBookmarks(sentences: sentences, figures: figures);
}
