/// Practice-only bookmark persistence (isolated from reader `asr.bookmarks.v1`).
///
/// Same [BookmarksStore] JSON shape / paper keys (`cache:<id>`), different prefs.
library;

import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import 'bookmark_models.dart';

const kPracticeBookmarksPrefsKey = 'asr.practice_bookmarks.v1';

String practiceBookmarksPrefsKey(String? uid) {
  final u = (uid ?? '').trim().replaceAll(RegExp(r'[^A-Za-z0-9_\-]'), '');
  if (u.isEmpty) return kPracticeBookmarksPrefsKey;
  final safe = u.length > 128 ? u.substring(0, 128) : u;
  return '$kPracticeBookmarksPrefsKey.u.$safe';
}

Future<BookmarksStore> loadPracticeBookmarksStore({required String? uid}) async {
  final p = await SharedPreferences.getInstance();
  final raw = p.getString(practiceBookmarksPrefsKey(uid));
  if (raw == null || raw.isEmpty) return BookmarksStore.empty();
  try {
    return BookmarksStore.fromJson(jsonDecode(raw));
  } catch (_) {
    return BookmarksStore.empty();
  }
}

Future<void> savePracticeBookmarksStore({
  required String? uid,
  required BookmarksStore store,
}) async {
  final p = await SharedPreferences.getInstance();
  final compact = compactBookmarksStore(store);
  await p.setString(
    practiceBookmarksPrefsKey(uid),
    jsonEncode(compact.toJson()),
  );
}
