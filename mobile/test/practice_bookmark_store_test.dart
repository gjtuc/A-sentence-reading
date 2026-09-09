import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/bookmark_models.dart';
import 'package:sentence_reading/api/practice_bookmark_store.dart';

void main() {
  test('practice prefs key is isolated from reader bookmarks', () {
    expect(practiceBookmarksPrefsKey('u1'), isNot(bookmarksPrefsKey('u1')));
    expect(
      practiceBookmarksPrefsKey('u1'),
      'asr.practice_bookmarks.v1.u.u1',
    );
    expect(bookmarksPrefsKey('u1'), 'asr.bookmarks.v1.u.u1');
  });
}
