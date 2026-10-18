/// design/411 — web reader text size and line width, after Word's Immersive Reader.
/// design/414 — page colour, spacing, book font, centred sentence, idle chrome,
/// and the faded neighbour sentences.
///
/// A wide monitor shows one sentence, so the web reader sets large type and keeps
/// the line inside a centred column instead of running edge to edge. The phone
/// look is unchanged: [webReadingStyle] returns null off the web or in a narrow
/// window.
library;

import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

enum WebTextSize { normal, large, huge }

enum WebColumnWidth { narrow, medium, wide }

/// [app] keeps the app theme; the others repaint the reader only.
enum WebPage { app, dim, paper, white }

enum WebSpacing { normal, wide }

enum WebFont { sans, serif }

const Map<WebTextSize, double> kWebTextPx = {
  WebTextSize.normal: 26,
  WebTextSize.large: 34,
  WebTextSize.huge: 44,
};

/// Column width in em. English averages about half an em per character, so
/// medium is roughly 68 characters a line.
const Map<WebColumnWidth, double> kWebColumnEm = {
  WebColumnWidth.narrow: 26,
  WebColumnWidth.medium: 34,
  WebColumnWidth.wide: 44,
};

const double kWebReadingMinWidth = 720;
const double kWebLineHeight = 1.6;
const double kWebWideLineHeight = 1.9;

/// Declared in pubspec.yaml (assets/fonts, SIL Open Font License).
const String kWebSerifFamily = 'SourceSerif4';

/// Seconds without a mouse move before the reader hides its buttons.
const Duration kWebChromeIdle = Duration(seconds: 3);

/// The neighbour sentences sit at this opacity.
const double kWebContextOpacity = 0.32;

/// Above the middle reads as the middle; dead centre looks low.
const Alignment kWebSentenceAlign = Alignment(0, -0.2);

class WebPagePalette {
  const WebPagePalette({
    required this.brightness,
    required this.background,
    required this.card,
    required this.text,
    required this.muted,
  });

  final Brightness brightness;
  final Color background;
  final Color card;
  final Color text;
  final Color muted;
}

const Map<WebPage, WebPagePalette> kWebPages = {
  WebPage.dim: WebPagePalette(
    brightness: Brightness.dark,
    background: Color(0xFF1B1C1F),
    card: Color(0xFF232428),
    text: Color(0xFFE3E1DC),
    muted: Color(0xFF98968F),
  ),
  WebPage.paper: WebPagePalette(
    brightness: Brightness.light,
    background: Color(0xFFEDE4CF),
    card: Color(0xFFF7F0E0),
    text: Color(0xFF3A3025),
    muted: Color(0xFF85765F),
  ),
  WebPage.white: WebPagePalette(
    brightness: Brightness.light,
    background: Color(0xFFF1F1F1),
    card: Color(0xFFFFFFFF),
    text: Color(0xFF1F1F1F),
    muted: Color(0xFF6E6E6E),
  ),
};

class WebReadingStyle {
  const WebReadingStyle({
    required this.fontSize,
    required this.maxWidth,
    this.lineHeight = kWebLineHeight,
    this.letterSpacing = 0.2,
    this.wordSpacing = 0,
    this.fontFamily,
    this.viewHeight = 0,
    this.showContext = false,
  });

  final double fontSize;
  final double maxWidth;
  final double lineHeight;
  final double letterSpacing;
  final double wordSpacing;
  final String? fontFamily;

  /// Height of the reading frame; the sentence is centred inside it.
  final double viewHeight;
  final bool showContext;
}

WebReadingStyle? webReadingStyle({
  required bool web,
  required double width,
  double height = 0,
  WebTextSize size = WebTextSize.large,
  WebColumnWidth column = WebColumnWidth.medium,
  WebSpacing spacing = WebSpacing.normal,
  WebFont font = WebFont.sans,
  bool showContext = false,
}) {
  if (!web || !width.isFinite || width < kWebReadingMinWidth) return null;
  final px = math.min(kWebTextPx[size]!, width / 18);
  final maxWidth = math.min(px * kWebColumnEm[column]!, width - 32);
  final wide = spacing == WebSpacing.wide;
  return WebReadingStyle(
    fontSize: px,
    maxWidth: maxWidth,
    lineHeight: wide ? kWebWideLineHeight : kWebLineHeight,
    letterSpacing: wide ? px * 0.05 : 0.2,
    wordSpacing: wide ? px * 0.2 : 0,
    fontFamily: font == WebFont.serif ? kWebSerifFamily : null,
    viewHeight: height.isFinite ? math.max(0, height) : 0,
    showContext: showContext,
  );
}

TextStyle webSentenceStyle(WebReadingStyle? web, TextStyle base) => web == null
    ? base
    : base.copyWith(
        fontSize: web.fontSize,
        height: web.lineHeight,
        letterSpacing: web.letterSpacing,
        wordSpacing: web.wordSpacing,
        fontFamily: web.fontFamily,
      );

TextStyle webKoStyle(WebReadingStyle? web, TextStyle base) => web == null
    ? base
    : base.copyWith(fontSize: web.fontSize * 0.72, height: web.lineHeight);

/// A neighbour sentence: smaller, faded, a few lines at most.
TextStyle webContextStyle(WebReadingStyle web, TextStyle base) =>
    webSentenceStyle(web, base).copyWith(fontSize: web.fontSize * 0.78);

/// Centres [child] in the web column; returns [child] untouched on the phone.
Widget webReadingColumn(WebReadingStyle? web, Widget child) {
  if (web == null) return child;
  return ConstrainedBox(
    constraints: BoxConstraints(minHeight: web.viewHeight),
    child: Align(
      alignment: kWebSentenceAlign,
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: web.maxWidth),
        child: Padding(
          padding: const EdgeInsets.only(top: 24, bottom: 24),
          child: child,
        ),
      ),
    ),
  );
}

/// Whether the reader in a window this wide should use the web look at all.
bool webReadingActive({required bool web, required double width}) =>
    web && width.isFinite && width >= kWebReadingMinWidth;

/// The app theme with the page colours laid over it.
ThemeData webPageTheme(ThemeData base, WebPagePalette p) {
  final scheme = ColorScheme.fromSeed(
    seedColor: base.colorScheme.primary,
    brightness: p.brightness,
  ).copyWith(
    surface: p.card,
    onSurface: p.text,
    onSurfaceVariant: p.muted,
    surfaceContainerLowest: p.background,
    surfaceContainerLow: p.card,
    surfaceContainer: p.card,
    surfaceContainerHigh: p.card,
    surfaceContainerHighest: p.card,
  );
  return base.copyWith(
    colorScheme: scheme,
    scaffoldBackgroundColor: p.background,
    canvasColor: p.background,
    cardColor: p.card,
    dividerColor: p.muted.withValues(alpha: 0.3),
    iconTheme: base.iconTheme.copyWith(color: p.text),
    textTheme: base.textTheme.apply(bodyColor: p.text, displayColor: p.text),
  );
}

/// Repaints [child] with the chosen page colour on a wide web window.
class WebPageTheme extends StatelessWidget {
  const WebPageTheme({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final prefs = WebReadingPrefs.instance;
    return ListenableBuilder(
      listenable: prefs,
      builder: (context, _) => LayoutBuilder(
        builder: (context, box) {
          final palette = kWebPages[prefs.page];
          if (palette == null || !webReadingActive(web: kIsWeb, width: box.maxWidth)) {
            return child;
          }
          // Material, not a bare box: it also resets DefaultTextStyle to the page text colour.
          return Theme(
            data: webPageTheme(Theme.of(context), palette),
            child: Material(color: palette.background, child: child),
          );
        },
      ),
    );
  }
}

/// Rebuilds with the style for the size it gets and the current prefs.
class WebReadingFrame extends StatelessWidget {
  const WebReadingFrame({super.key, required this.builder});

  final Widget Function(BuildContext context, WebReadingStyle? web) builder;

  @override
  Widget build(BuildContext context) {
    final prefs = WebReadingPrefs.instance;
    return ListenableBuilder(
      listenable: prefs,
      builder: (context, _) => LayoutBuilder(
        builder: (context, box) => builder(
          context,
          webReadingStyle(
            web: kIsWeb,
            width: box.maxWidth,
            height: box.maxHeight,
            size: prefs.size,
            column: prefs.column,
            spacing: prefs.spacing,
            font: prefs.font,
            showContext: prefs.showContext,
          ),
        ),
      ),
    );
  }
}

class WebReadingPrefs extends ChangeNotifier {
  WebReadingPrefs._();

  static final WebReadingPrefs instance = WebReadingPrefs._();

  static const String sizeKey = 'web_reading_size_v1';
  static const String columnKey = 'web_reading_column_v1';
  static const String pageKey = 'web_reading_page_v1';
  static const String spacingKey = 'web_reading_spacing_v1';
  static const String fontKey = 'web_reading_font_v1';
  static const String autoHideKey = 'web_reading_autohide_v1';
  static const String contextKey = 'web_reading_context_v1';

  WebTextSize size = WebTextSize.large;
  WebColumnWidth column = WebColumnWidth.medium;
  WebPage page = WebPage.dim;
  WebSpacing spacing = WebSpacing.normal;
  WebFont font = WebFont.sans;
  bool autoHide = true;
  bool showContext = true;
  Future<void>? _loading;

  Future<void> load() => _loading ??= _load();

  Future<void> _load() async {
    try {
      final p = await SharedPreferences.getInstance();
      size = WebTextSize.values.asNameMap()[p.getString(sizeKey) ?? ''] ?? size;
      column = WebColumnWidth.values.asNameMap()[p.getString(columnKey) ?? ''] ?? column;
      page = WebPage.values.asNameMap()[p.getString(pageKey) ?? ''] ?? page;
      spacing = WebSpacing.values.asNameMap()[p.getString(spacingKey) ?? ''] ?? spacing;
      font = WebFont.values.asNameMap()[p.getString(fontKey) ?? ''] ?? font;
      autoHide = p.getBool(autoHideKey) ?? autoHide;
      showContext = p.getBool(contextKey) ?? showContext;
      notifyListeners();
    } catch (_) {}
  }

  Future<void> _saveString(String key, String value) async {
    try {
      final p = await SharedPreferences.getInstance();
      await p.setString(key, value);
    } catch (_) {}
  }

  Future<void> _saveBool(String key, bool value) async {
    try {
      final p = await SharedPreferences.getInstance();
      await p.setBool(key, value);
    } catch (_) {}
  }

  Future<void> setSize(WebTextSize next) async {
    if (next == size) return;
    size = next;
    notifyListeners();
    await _saveString(sizeKey, next.name);
  }

  Future<void> setColumn(WebColumnWidth next) async {
    if (next == column) return;
    column = next;
    notifyListeners();
    await _saveString(columnKey, next.name);
  }

  Future<void> setPage(WebPage next) async {
    if (next == page) return;
    page = next;
    notifyListeners();
    await _saveString(pageKey, next.name);
  }

  Future<void> setSpacing(WebSpacing next) async {
    if (next == spacing) return;
    spacing = next;
    notifyListeners();
    await _saveString(spacingKey, next.name);
  }

  Future<void> setFont(WebFont next) async {
    if (next == font) return;
    font = next;
    notifyListeners();
    await _saveString(fontKey, next.name);
  }

  Future<void> setAutoHide(bool next) async {
    if (next == autoHide) return;
    autoHide = next;
    notifyListeners();
    await _saveBool(autoHideKey, next);
  }

  Future<void> setShowContext(bool next) async {
    if (next == showContext) return;
    showContext = next;
    notifyListeners();
    await _saveBool(contextKey, next);
  }

  @visibleForTesting
  void resetForTests() {
    size = WebTextSize.large;
    column = WebColumnWidth.medium;
    page = WebPage.dim;
    spacing = WebSpacing.normal;
    font = WebFont.sans;
    autoHide = true;
    showContext = true;
    _loading = null;
  }
}
