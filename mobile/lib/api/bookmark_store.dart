/// Local uid-scoped bookmark store (GCS sync cache).
library;

import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import 'bookmark_models.dart';
import 'progress_store.dart';

Future<BookmarksStore> loadBookmarksStore({required String? uid}) async {
  final p = await SharedPreferences.getInstance();
  final raw = p.getString(bookmarksPrefsKey(uid));
  if (raw == null || raw.isEmpty) return BookmarksStore.empty();
  try {
    return BookmarksStore.fromJson(jsonDecode(raw));
  } catch (_) {
    return BookmarksStore.empty();
  }
}

Future<void> saveBookmarksStore({
  required String? uid,
  required BookmarksStore store,
}) async {
  final p = await SharedPreferences.getInstance();
  final compact = compactBookmarksStore(store);
  await p.setString(bookmarksPrefsKey(uid), jsonEncode(compact.toJson()));
}

Future<PaperBookmarks?> loadPaperBookmarks({
  required String? uid,
  required String cacheId,
}) async {
  final store = await loadBookmarksStore(uid: uid);
  return store.papers[bookmarkPaperKey(cacheId)];
}

Future<void> savePaperBookmarks({
  required String? uid,
  required String cacheId,
  required PaperBookmarks? paper,
}) async {
  final store = await loadBookmarksStore(uid: uid);
  final pk = bookmarkPaperKey(cacheId);
  final papers = Map<String, PaperBookmarks>.from(store.papers);
  if (paper == null ||
      (paper.sentences.isEmpty && paper.figures.isEmpty)) {
    papers.remove(pk);
  } else {
    papers[pk] = compactPaperBookmarks(paper);
  }
  await saveBookmarksStore(
    uid: uid,
    store: BookmarksStore(papers: papers),
  );
}

Future<void> purgePaperBookmarks({
  required String? uid,
  required String cacheId,
}) async {
  await savePaperBookmarks(uid: uid, cacheId: cacheId, paper: null);
}

/// Alias for progress paper key convention.
String bookmarkCacheKey(String cacheId) => progressCacheKey(cacheId);
