/// Practice sentence bookmarks — local-only, never touches reader BookmarkController.
library;

import 'package:flutter/foundation.dart';

import '../api/bookmark_models.dart';
import '../api/practice_bookmark_store.dart';
import '../api/reader_nav_labels.dart';

class PracticeBookmarkController extends ChangeNotifier {
  String? _uid;
  String? _cacheId;
  PaperBookmarks _paper = const PaperBookmarks();
  BookmarksStore _store = BookmarksStore.empty();
  bool ready = false;

  Set<String> get activeSentenceKeys => _paper.activeSentenceKeys;
  bool get canBookmark => _uid != null;
  String? get boundUid => _uid;

  Future<void> bindUid(String? uid) async {
    _uid = (uid ?? '').trim().isEmpty ? null : uid!.trim();
    _store = await loadPracticeBookmarksStore(uid: _uid);
    _reloadPaperFromStore();
    ready = true;
    notifyListeners();
  }

  Future<void> loadPaper(String cacheId) async {
    final cid = cacheId.trim();
    if (cid.isEmpty) return;
    _cacheId = cid;
    _store = await loadPracticeBookmarksStore(uid: _uid);
    _reloadPaperFromStore();
    notifyListeners();
  }

  bool isSentenceBookmarked(String? key) {
    if (key == null || key.isEmpty) return false;
    return _paper.activeSentenceKeys.contains(key);
  }

  int sectionBadgeCount(SectionNavIndex nav, int globalIndex) {
    final (sectionIndex, _) = nav.selectionForGlobal(globalIndex);
    return nav.sectionBookmarkCount(activeSentenceKeys, sectionIndex);
  }

  bool pickerSentenceHighlighted(
    SectionNavIndex nav,
    int sectionIndex,
    int positionIndex,
  ) {
    final key = nav.sentenceBookmarkKeyForSelection(sectionIndex, positionIndex);
    return isSentenceBookmarked(key);
  }

  int pickerSectionBadgeCount(SectionNavIndex nav, int sectionIndex) {
    return nav.sectionBookmarkCount(activeSentenceKeys, sectionIndex);
  }

  /// Returns true if bookmark was added, false if removed.
  Future<bool> toggleSentenceBookmark(
    SectionNavIndex nav,
    int globalIndex,
  ) async {
    final key = nav.sentenceBookmarkKeyForGlobal(globalIndex);
    if (key == null) return false;
    final wasActive = isSentenceBookmarked(key);
    final events = Map<String, BookmarkEvent>.from(_paper.sentences);
    events[key] = bookmarkEventNow(deleted: wasActive);
    _paper = _paper.copyWith(sentences: events, figures: const {});
    await _persistPaper();
    notifyListeners();
    return !wasActive;
  }

  Future<void> purgePaper(String cacheId) async {
    final cid = cacheId.trim();
    if (cid.isEmpty) return;
    final pk = bookmarkPaperKey(cid);
    final papers = Map<String, PaperBookmarks>.from(_store.papers);
    papers.remove(pk);
    _store = BookmarksStore(papers: papers);
    await savePracticeBookmarksStore(uid: _uid, store: _store);
    if (_cacheId == cid) {
      _paper = const PaperBookmarks();
    }
    notifyListeners();
  }

  void _reloadPaperFromStore() {
    final cid = _cacheId;
    if (cid == null || cid.isEmpty) {
      _paper = const PaperBookmarks();
      return;
    }
    _paper = _store.papers[bookmarkPaperKey(cid)] ?? const PaperBookmarks();
  }

  Future<void> _persistPaper() async {
    final cid = _cacheId;
    if (cid == null || cid.isEmpty) return;
    final pk = bookmarkPaperKey(cid);
    final papers = Map<String, PaperBookmarks>.from(_store.papers);
    final compact = compactPaperBookmarks(_paper);
    if (compact.sentences.isEmpty && compact.figures.isEmpty) {
      papers.remove(pk);
    } else {
      // Practice store: sentences only (drop any figure noise).
      papers[pk] = PaperBookmarks(sentences: compact.sentences);
    }
    _store = BookmarksStore(papers: papers);
    await savePracticeBookmarksStore(uid: _uid, store: _store);
  }
}
