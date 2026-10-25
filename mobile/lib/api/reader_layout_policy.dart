/// design/183 — first matched Fig/Table chip sentence index + layout policy.
library;

import 'fig_refs.dart';
import 'reading_models.dart';

/// Same predicate as [_figRefChipRow] / [hintsForSentence].
int? firstFigTableChipSentenceIndex({
  required List<SentenceView> sentences,
  required List<FigureView> figures,
  bool supplementaryMerged = false,
}) {
  final captions = figures.map((f) => f.caption).toList();
  final slotKeys = figures.map((f) => f.slotKey).toList();
  for (var i = 0; i < sentences.length; i++) {
    final text = sentences[i].text;
    if (text.trim().isEmpty) continue;
    final hints = hintsForSentence(
      text: text,
      captions: captions,
      slotKeys: slotKeys,
      supplementaryMerged: supplementaryMerged,
    );
    if (hints.isNotEmpty) return i;
  }
  return null;
}

enum ReaderLayoutAutoMode { auto, userPinned }

enum ReaderLayoutDesire { sentenceOnly, splitDefault }

/// Pure policy for Intro collapse / Results expand (design/183).
class ReaderLayoutPolicy {
  ReaderLayoutAutoMode mode = ReaderLayoutAutoMode.auto;
  int? threshold;
  bool autoEnabled = true;

  /// design/459 — the reader folded the figure pane. A sentence that names a
  /// figure opens it; the next one that does not folds it again.
  bool folded = false;

  void resetForPaper({
    required int? threshold,
    required bool autoEnabled,
  }) {
    mode = ReaderLayoutAutoMode.auto;
    this.threshold = threshold;
    this.autoEnabled = autoEnabled;
    folded = false;
    // design/183 — cite expand/collapse is user-owned on ReaderScreen.
  }

  void pin() => mode = ReaderLayoutAutoMode.userPinned;

  /// design/183 — pin is a dwell override; sentence moves reclaim auto.
  void unpin() => mode = ReaderLayoutAutoMode.auto;

  bool get followsAuto => autoEnabled && mode == ReaderLayoutAutoMode.auto;

  ReaderLayoutDesire desireFor({
    required int sentenceIndex,
    required bool sectionIsTitle,
    required bool hasCover,
    bool namesFigure = false,
  }) {
    if (folded) {
      return namesFigure
          ? ReaderLayoutDesire.splitDefault
          : ReaderLayoutDesire.sentenceOnly;
    }
    if (sectionIsTitle && hasCover) {
      return ReaderLayoutDesire.splitDefault;
    }
    final t = threshold;
    if (t == null || sentenceIndex < t) {
      return ReaderLayoutDesire.sentenceOnly;
    }
    return ReaderLayoutDesire.splitDefault;
  }
}
