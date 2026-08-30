/// Reader bookmark state — local cache + GCS sync.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';

import '../api/bookmark_gate.dart';
import '../api/bookmark_models.dart';
import '../api/bookmark_store.dart';
import '../api/client.dart';
import '../api/reader_nav_labels.dart';

class BookmarkController extends ChangeNotifier {
  BookmarkController({AsrClient? client}) : _client = client;

  AsrClient? _client;
  String? _uid;
  String? _cacheId;
  PaperBookmarks _paper = const PaperBookmarks();
  BookmarksStore _store = BookmarksStore.empty();
  bool serverAvailable = false;
  bool ready = false;
  Timer? _pushTimer;

  Set<String> get activeSentenceKeys => _paper.activeSentenceKeys;
  Set<String> get activeFigureKeys => _paper.activeFigureKeys;
  bool get canBookmark => _uid != null;

  void attachClient(AsrClient client) => _client = client;

  Future<void> bindUid(String? uid) async {
    _uid = (uid ?? '').trim().isEmpty ? null : uid!.trim();
    _store = await loadBookmarksStore(uid: _uid);
    _reloadPaperFromStore();
    ready = true;
    notifyListeners();
  }

  void clearSession() {
    _uid = null;
    _cacheId = null;
    _paper = const PaperBookmarks();
    _store = BookmarksStore.empty();
    _pushTimer?.cancel();
    ready = false;
    notifyListeners();
  }

  void setServerAvailable(bool next) {
    if (serverAvailable == next) return;
    serverAvailable = next;
    notifyListeners();
  }

  Future<void> loadPaper(String cacheId) async {
    final cid = cacheId.trim();
    if (cid.isEmpty) return;
    _cacheId = cid;
    _store = await loadBookmarksStore(uid: _uid);
    _reloadPaperFromStore();
    notifyListeners();
  }

  Future<void> applyNavPrune({
    required SectionNavIndex sectionNav,
    required FigureNavIndex figureNav,
  }) async {
    if (_cacheId == null) return;
    final pruned = prunePaperBookmarks(
      paper: _paper,
      sectionNav: sectionNav,
      figureNav: figureNav,
    );
    if (pruned.sentences.length == _paper.sentences.length &&
        pruned.figures.length == _paper.figures.length &&
        pruned.activeSentenceKeys.length ==
            _paper.activeSentenceKeys.length &&
        pruned.activeFigureKeys.length == _paper.activeFigureKeys.length) {
      return;
    }
    _paper = pruned;
    await _persistPaper();
    notifyListeners();
  }

  Future<void> pullFromServer() async {
    final client = _client;
    if (client == null || _uid == null || !serverAvailable) return;
    try {
      final remote = await client.fetchBookmarksSync();
      if (!remote.available || remote.store == null) return;
      final remoteStore = BookmarksStore.fromJson(remote.store);
      _store = mergeBookmarksStores(_store, remoteStore);
      await saveBookmarksStore(uid: _uid, store: _store);
      _reloadPaperFromStore();
      notifyListeners();
    } catch (_) {
      // EDGE: offline — keep local.
    }
  }

  Future<void> pushToServer() async {
    final client = _client;
    if (client == null || _uid == null || !serverAvailable) return;
    try {
      final result = await client.pushBookmarksSync(_store.toJson());
      if (!result.available || result.store == null) return;
      _store = BookmarksStore.fromJson(result.store);
      await saveBookmarksStore(uid: _uid, store: _store);
      _reloadPaperFromStore();
      notifyListeners();
    } catch (_) {
      // EDGE: retry on next lifecycle.
    }
  }

  void schedulePush() {
    _pushTimer?.cancel();
    _pushTimer = Timer(const Duration(milliseconds: 500), () {
      unawaited(pushToServer());
    });
  }

  bool isSentenceBookmarked(String? key) {
    if (key == null || key.isEmpty) return false;
    return _paper.activeSentenceKeys.contains(key);
  }

  bool isFigureBookmarked(String? key) {
    if (key == null || key.isEmpty) return false;
    return _paper.activeFigureKeys.contains(key);
  }

  int sectionBadgeCount(SectionNavIndex nav, int globalIndex) {
    final (sectionIndex, _) = nav.selectionForGlobal(globalIndex);
    return nav.sectionBookmarkCount(activeSentenceKeys, sectionIndex);
  }

  int kindBadgeCount(FigureNavIndex nav, int carouselIndex) {
    final (kindIndex, _) = nav.selectionForCarousel(carouselIndex);
    return nav.kindBookmarkCount(activeFigureKeys, kindIndex);
  }

  bool pickerSentenceHighlighted(
    SectionNavIndex nav,
    int sectionIndex,
    int positionIndex,
  ) {
    final key = nav.sentenceBookmarkKeyForSelection(sectionIndex, positionIndex);
    return isSentenceBookmarked(key);
  }

  bool pickerFigureHighlighted(
    FigureNavIndex nav,
    int kindIndex,
    int numberIndex,
  ) {
    final key = nav.figureBookmarkKeyForSelection(kindIndex, numberIndex);
    return isFigureBookmarked(key);
  }

  int pickerSectionBadgeCount(SectionNavIndex nav, int sectionIndex) {
    return nav.sectionBookmarkCount(activeSentenceKeys, sectionIndex);
  }

  int pickerKindBadgeCount(FigureNavIndex nav, int kindIndex) {
    return nav.kindBookmarkCount(activeFigureKeys, kindIndex);
  }

  /// Total active sentence + figure bookmarks for a library paper (by cache id).
  int paperBookmarkCount(String cacheId) {
    final cid = cacheId.trim();
    if (cid.isEmpty) return 0;
    return (_store.papers[bookmarkPaperKey(cid)] ?? const PaperBookmarks())
        .totalActiveCount;
  }

  /// Returns true if bookmark was added, false if removed.
  Future<bool> toggleSentenceBookmark(SectionNavIndex nav, int globalIndex) async {
    final key = nav.sentenceBookmarkKeyForGlobal(globalIndex);
    if (key == null) return false;
    final wasActive = isSentenceBookmarked(key);
    final events = Map<String, BookmarkEvent>.from(_paper.sentences);
    events[key] = bookmarkEventNow(deleted: wasActive);
    _paper = _paper.copyWith(sentences: events);
    await _persistPaper();
    schedulePush();
    notifyListeners();
    return !wasActive;
  }

  Future<bool> toggleFigureBookmark(FigureNavIndex nav, int carouselIndex) async {
    final key = nav.figureBookmarkKeyForCarousel(carouselIndex);
    if (key == null) return false;
    final wasActive = isFigureBookmarked(key);
    final events = Map<String, BookmarkEvent>.from(_paper.figures);
    events[key] = bookmarkEventNow(deleted: wasActive);
    _paper = _paper.copyWith(figures: events);
    await _persistPaper();
    schedulePush();
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
    await saveBookmarksStore(uid: _uid, store: _store);
    if (_cacheId == cid) {
      _paper = const PaperBookmarks();
    }
    schedulePush();
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
      papers[pk] = _paper;
    }
    _store = BookmarksStore(papers: papers);
    await saveBookmarksStore(uid: _uid, store: _store);
  }

  @override
  void dispose() {
    _pushTimer?.cancel();
    super.dispose();
  }
}
