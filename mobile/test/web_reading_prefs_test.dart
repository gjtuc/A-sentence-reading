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

  test('design/414 wide spacing and the book font reach the sentence style', () {
    final s = webReadingStyle(
      web: true,
      width: 1900,
      height: 900,
      spacing: WebSpacing.wide,
      font: WebFont.serif,
      showContext: true,
    )!;
    expect(s.lineHeight, kWebWideLineHeight);
    expect(s.letterSpacing, closeTo(34 * 0.05, 1e-9));
    expect(s.wordSpacing, closeTo(34 * 0.2, 1e-9));
    expect(s.viewHeight, 900);
    expect(s.showContext, isTrue);
    final t = webSentenceStyle(s, const TextStyle(fontSize: 18));
    expect(t.fontFamily, kWebSerifFamily);
    expect(t.wordSpacing, closeTo(34 * 0.2, 1e-9));
    expect(webContextStyle(s, const TextStyle(fontSize: 18)).fontSize, closeTo(34 * 0.78, 1e-9));
    final plain = webReadingStyle(web: true, width: 1900, height: double.infinity)!;
    expect(plain.fontFamily, isNull);
    expect(plain.wordSpacing, 0);
    expect(plain.viewHeight, 0);
  });

  testWidgets('design/414 the sentence sits in the middle of the frame', (tester) async {
    const web = WebReadingStyle(fontSize: 34, maxWidth: 600, viewHeight: 800);
    await tester.pumpWidget(Directionality(
      textDirection: TextDirection.ltr,
      child: Align(
        alignment: Alignment.topLeft,
        child: SizedBox(
          width: 800,
          child: SingleChildScrollView(
            child: webReadingColumn(web, const SizedBox(key: Key('s'), width: 600, height: 100)),
          ),
        ),
      ),
    ));
    final box = tester.getRect(find.byKey(const Key('s')));
    expect(box.left, 100);
    final free = 800 - 100 - 48;
    final top = 24 + free * (1 + kWebSentenceAlign.y) / 2;
    expect(box.top, closeTo(top, 0.5));
    expect(box.center.dy, lessThan(400));
  });

  test('design/414 page, spacing, font and switches load and save', () async {
    SharedPreferences.setMockInitialValues({
      WebReadingPrefs.pageKey: 'paper',
      WebReadingPrefs.spacingKey: 'wide',
      WebReadingPrefs.fontKey: 'serif',
      WebReadingPrefs.autoHideKey: false,
      WebReadingPrefs.contextKey: false,
    });
    final prefs = WebReadingPrefs.instance..resetForTests();
    expect(prefs.page, WebPage.dim);
    expect(prefs.autoHide, isTrue);
    expect(prefs.showContext, isTrue);
    await prefs.load();
    expect(prefs.page, WebPage.paper);
    expect(prefs.spacing, WebSpacing.wide);
    expect(prefs.font, WebFont.serif);
    expect(prefs.autoHide, isFalse);
    expect(prefs.showContext, isFalse);
    await prefs.setPage(WebPage.white);
    await prefs.setAutoHide(true);
    final p = await SharedPreferences.getInstance();
    expect(p.getString(WebReadingPrefs.pageKey), 'white');
    expect(p.getBool(WebReadingPrefs.autoHideKey), isTrue);
    prefs.resetForTests();
  });

  test('design/414 a page colour repaints the reader, app keeps the theme', () {
    expect(kWebPages[WebPage.app], isNull);
    final base = ThemeData(brightness: Brightness.dark);
    final paper = webPageTheme(base, kWebPages[WebPage.paper]!);
    expect(paper.colorScheme.brightness, Brightness.light);
    expect(paper.colorScheme.surfaceContainerLow, kWebPages[WebPage.paper]!.card);
    expect(paper.scaffoldBackgroundColor, kWebPages[WebPage.paper]!.background);
    expect(paper.textTheme.bodyMedium!.color, kWebPages[WebPage.paper]!.text);
    expect(webReadingActive(web: true, width: 719), isFalse);
    expect(webReadingActive(web: false, width: 1900), isFalse);
  });

  test('design/420: on the web the page colour is the app theme', () {
    expect(webThemeMode(WebPage.app), ThemeMode.system);
    expect(webThemeMode(WebPage.dim), ThemeMode.dark);
    expect(webThemeMode(WebPage.paper), ThemeMode.light);
    expect(webThemeMode(WebPage.white), ThemeMode.light);
    final light = ThemeData(
      colorScheme: ColorScheme.fromSeed(seedColor: Colors.teal),
      useMaterial3: true,
    );
    final dark = ThemeData(
      colorScheme: ColorScheme.fromSeed(
        seedColor: Colors.teal,
        brightness: Brightness.dark,
      ),
      useMaterial3: true,
    );
    expect(identical(webAppTheme(light, WebPage.app), light), isTrue);
    expect(identical(webAppTheme(dark, WebPage.paper), dark), isTrue,
        reason: 'a light page leaves the unused dark theme alone');
    expect(webAppTheme(light, WebPage.paper).scaffoldBackgroundColor,
        kWebPages[WebPage.paper]!.background);
    expect(webAppTheme(dark, WebPage.dim).scaffoldBackgroundColor,
        kWebPages[WebPage.dim]!.background);
  });

  test('design/420: the figure window does not open on its own until asked', () async {
    SharedPreferences.setMockInitialValues({});
    final prefs = WebReadingPrefs.instance..resetForTests();
    await prefs.load();
    expect(prefs.autoFigurePane, isFalse);
    await prefs.setAutoFigurePane(true);
    final p = await SharedPreferences.getInstance();
    expect(p.getBool(WebReadingPrefs.autoPaneKey), isTrue);
    prefs.resetForTests();
  });
}