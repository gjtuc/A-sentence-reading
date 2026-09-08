/// Reader bookmark state — local cache + GCS sync / design/187 device SoT.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/bookmark_gate.dart';
import '../api/bookmark_models.dart';
import '../api/bookmark_store.dart';
import '../api/client.dart';
import '../api/reader_nav_labels.dart';
import '../services/evidence_bus.dart';

class BookmarkController extends ChangeNotifier {
  BookmarkController({AsrClient? client}) : _client = client;

  AsrClient? _client;
  String? _uid;
  String? _cacheId;
  PaperBookmarks _paper = const PaperBookmarks();
  BookmarksStore _store = BookmarksStore.empty();
  bool serverAvailable = false;
  bool ready = false;
  /// design/187 — device is SoT; cloud PUT refused / push no-op.
  bool localSot = false;
  Timer? _pushTimer;

  Set<String> get activeSentenceKeys => _paper.activeSentenceKeys;
  Set<String> get activeFigureKeys => _paper.activeFigureKeys;
  bool get canBookmark => _uid != null;
  String? get boundUid => _uid;

  void attachClient(AsrClient client) => _client = client;

  void setLocalSot(bool next) {
    if (localSot == next) return;
    localSot = next;
    notifyListeners();
  }

  String _migratedPrefsKey() {
    final u = (_uid ?? '').trim().replaceAll(RegExp(r'[^A-Za-z0-9_\-]'), '');
    if (u.isEmpty) return 'asr.bookmarks.cloud_migrated.v1';
    final safe = u.length > 128 ? u.substring(0, 128) : u;
    return 'asr.bookmarks.cloud_migrated.v1.u.$safe';
  }

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
    localSot = false;
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
    if (localSot) {
      await _migrateOnce();
      return;
    }
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

  /// design/187 — one-shot GET sync → merge local → ack → wipe cloud.
  Future<void> _migrateOnce() async {
    final client = _client;
    if (client == null || _uid == null) return;
    try {
      final prefs = await SharedPreferences.getInstance();
      if (prefs.getBool(_migratedPrefsKey()) == true) return;

      asrEvidenceBus?.record(
        'bookmarks_local_migrate_start',
        severity: 'lifecycle',
        ok: true,
      );

      final remote = await client.fetchBookmarksSync();
      if (remote.available && remote.store != null) {
        final remoteStore = BookmarksStore.fromJson(remote.store);
        _store = mergeBookmarksStores(_store, remoteStore);
        await saveBookmarksStore(uid: _uid, store: _store);
        _reloadPaperFromStore();
        notifyListeners();
      }

      final paperN = _store.papers.length;
      final acked = await client.ackBookmarksLocalMigrate(paperN: paperN);
      if (acked) {
        await prefs.setBool(_migratedPrefsKey(), true);
      }
      asrEvidenceBus?.record(
        'bookmarks_local_migrate_done',
        severity: 'lifecycle',
        ok: acked,
        details: {'paper_n': paperN},
      );
    } catch (_) {
      asrEvidenceBus?.record(
        'bookmarks_local_migrate_done',
        severity: 'lifecycle',
        ok: false,
        code: 'exception',
      );
    }
  }

  Future<void> pushToServer() async {
    if (localSot) return;
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
    if (localSot) return;
    _pushTimer?.cancel();
    _pushTimer = Timer(const Duration(milliseconds: 500), () {
      unawaited(pushToServer());
    });
  }

  /// design/187 E — paper slice for transfer pack (`user/bookmarks.json`).
  Uint8List? exportPaperPackBytes(String cacheId) {
    final cid = cacheId.trim();
    if (cid.isEmpty) return null;
    final paper = _store.papers[bookmarkPaperKey(cid)];
    if (paper == null) return null;
    if (paper.sentences.isEmpty && paper.figures.isEmpty) return null;
    return Uint8List.fromList(utf8.encode(jsonEncode(paper.toJson())));
  }

  /// design/187 E — restore paper slice from transfer pack.
  Future<void> importPaperPackJson(
    String cacheId,
    Map<String, dynamic> json,
  ) async {
    final cid = cacheId.trim();
    if (cid.isEmpty || _uid == null) return;
    final incoming = PaperBookmarks.fromJson(json);
    final pk = bookmarkPaperKey(cid);
    final papers = Map<String, PaperBookmarks>.from(_store.papers);
    final prev = papers[pk] ?? const PaperBookmarks();
    papers[pk] = mergePaperBookmarks(prev, incoming);
    _store = BookmarksStore(papers: papers);
    await saveBookmarksStore(uid: _uid, store: _store);
    if (_cacheId == cid) {
      _reloadPaperFromStore();
    }
    notifyListeners();
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
