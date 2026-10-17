// design/411 - web reader type and line width (Word Immersive Reader style).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/state/web_reading_prefs.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  test('the phone and narrow windows keep the phone look', () {
    expect(webReadingStyle(web: false, width: 1900), isNull);
    expect(webReadingStyle(web: true, width: 700), isNull);
    expect(webReadingStyle(web: true, width: double.infinity), isNull);
    final base = const TextStyle(fontSize: 18);
    expect(webSentenceStyle(null, base), same(base));
    final child = const SizedBox();
    expect(webReadingColumn(null, child), same(child));
  });

  test('a wide monitor gets large type in a centred column', () {
    final s = webReadingStyle(web: true, width: 1900)!;
    expect(s.fontSize, 34);
    expect(s.maxWidth, 34 * 34);
    expect(s.lineHeight, 1.6);
    final huge = webReadingStyle(web: true, width: 1900, size: WebTextSize.huge, column: WebColumnWidth.wide)!;
    expect(huge.fontSize, 44);
    expect(huge.maxWidth, 1900 - 32);
    expect(webSentenceStyle(s, const TextStyle(fontSize: 18)).fontSize, 34);
    expect(webKoStyle(s, const TextStyle(fontSize: 14)).fontSize, closeTo(34 * 0.72, 1e-9));
  });

  test('type shrinks with the window so a line still holds words', () {
    final s = webReadingStyle(web: true, width: 760, size: WebTextSize.huge)!;
    expect(s.fontSize, closeTo(760 / 18, 1e-9));
    expect(s.maxWidth, lessThanOrEqualTo(760 - 32));
  });

  test('prefs load and save by name', () async {
    SharedPreferences.setMockInitialValues({WebReadingPrefs.sizeKey: 'huge', WebReadingPrefs.columnKey: 'narrow'});
    final prefs = WebReadingPrefs.instance..resetForTests();
    await prefs.load();
    expect(prefs.size, WebTextSize.huge);
    expect(prefs.column, WebColumnWidth.narrow);
    await prefs.setSize(WebTextSize.normal);
    await prefs.setColumn(WebColumnWidth.wide);
    final p = await SharedPreferences.getInstance();
    expect(p.getString(WebReadingPrefs.sizeKey), 'normal');
    expect(p.getString(WebReadingPrefs.columnKey), 'wide');
    prefs.resetForTests();
  });
}