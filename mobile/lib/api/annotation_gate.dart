/// Validate annotation keys against current session nav indices (fail-closed prune).
library;

import 'annotation_models.dart';
import 'reader_nav_labels.dart';

PaperAnnotations prunePaperAnnotations({
  required PaperAnnotations paper,
  required SectionNavIndex sectionNav,
  required FigureNavIndex figureNav,
}) {
  final sentences = <String, List<AnnotationEvent>>{};
  for (final entry in paper.sentences.entries) {
    if (sectionNav.isValidSentenceBookmarkKey(entry.key)) {
      final active = entry.value.where((e) => e.isActive).toList();
      if (active.isNotEmpty) sentences[entry.key] = active;
    }
  }
  final figures = <String, List<AnnotationEvent>>{};
  for (final entry in paper.figures.entries) {
    if (figureNav.isValidFigureBookmarkKey(entry.key)) {
      final active = entry.value.where((e) => e.isActive).toList();
      if (active.isNotEmpty) figures[entry.key] = active;
    }
  }
  return PaperAnnotations(sentences: sentences, figures: figures);
}
