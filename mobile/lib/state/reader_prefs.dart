/// design/435 — the phone sentence size and the split the reader last left.
/// design/436 — the phone page colour, and the phone sentence style from the
/// shared reading prefs (font, line height, spacing, line width).
///
/// The web reader has its own sizes ([WebReadingPrefs]); these apply where the
/// web look is off, which is the phone.
library;

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'web_reading_prefs.dart';

/// The phone sentence before this setting existed (Material titleMedium).
const double kSentencePxDefault = 16;
const double kSentencePxMin = 16;
const double kSentencePxMax = 40;
const int kSentencePxSteps = 12;

/// The split bar starts here until the reader moves it (design/98 magnet).
const double kSplitFractionDefault = 0.6;

/// A saved split outside this band would open as a sliver; keep the default.
const double kSplitFractionMin = 0.15;
const double kSplitFractionMax = 0.85;

/// Korean under the sentence keeps the old 14 : 16 ratio.
double koPxFor(double sentencePx) => sentencePx * 14 / 16;

/// Phone line height; null keeps the theme's (1.5 for titleMedium).
const Map<WebLineGap, double?> kPhoneLineHeight = {
  WebLineGap.normal: null,
  WebLineGap.wide: kWebWideLineHeight,
  WebLineGap.wider: 2.2,
};

/// A phone line is the screen wide, so line width is the side margin inside the
/// sentence card. Medium plus the card's own 4 is the old 16.
const Map<WebColumnWidth, double> kPhoneColumnInset = {
  WebColumnWidth.narrow: 36,
  WebColumnWidth.medium: 12,
  WebColumnWidth.wide: 2,
};

/// The phone sentence, or the Korean under it when [px] is given.
TextStyle phoneSentenceStyle(TextStyle base, {double? px}) {
  final web = WebReadingPrefs.instance;
  final size = px ?? ReaderPrefs.instance.sentencePx;
  final wide = web.spacing == WebSpacing.wide;
  return base.copyWith(
    fontSize: size,
    height: kPhoneLineHeight[web.lineGap],
    letterSpacing: wide ? size * 0.05 : null,
    wordSpacing: wide ? size * 0.2 : null,
    fontFamily: kReadingFontFamily[web.font],
  );
}

double phoneColumnInset() => kPhoneColumnInset[WebReadingPrefs.instance.column]!;

class ReaderPrefs extends ChangeNotifier {
  ReaderPrefs._();

  static final ReaderPrefs instance = ReaderPrefs._();

  static const String sentencePxKey = 'reader_sentence_px_v1';
  static const String splitKey = 'reader_split_fraction_v1';
  static const String pageKey = 'reader_page_v1';

  double sentencePx = kSentencePxDefault;

  /// Not notified: the reader reads it when it next opens a split.
  double splitFraction = kSplitFractionDefault;

  /// [WebPage.app] follows the 테마 setting; the others paint every screen.
  WebPage page = WebPage.app;
  Future<void>? _loading;

  Future<void> load() => _loading ??= _load();

  Future<void> _load() async {
    try {
      final p = await SharedPreferences.getInstance();
      final px = p.getDouble(sentencePxKey);
      if (px != null && px.isFinite) {
        sentencePx = px.clamp(kSentencePxMin, kSentencePxMax).toDouble();
      }
      final f = p.getDouble(splitKey);
      if (f != null && f >= kSplitFractionMin && f <= kSplitFractionMax) {
        splitFraction = f;
      }
      page = WebPage.values.asNameMap()[p.getString(pageKey) ?? ''] ?? page;
      notifyListeners();
    } catch (_) {}
  }

  Future<void> _saveDouble(String key, double value) async {
    try {
      final p = await SharedPreferences.getInstance();
      await p.setDouble(key, value);
    } catch (_) {}
  }

  Future<void> setSentencePx(double next) async {
    final v = next.clamp(kSentencePxMin, kSentencePxMax).toDouble();
    if (v == sentencePx) return;
    sentencePx = v;
    notifyListeners();
    await _saveDouble(sentencePxKey, v);
  }

  /// A split outside the band is ignored; the bar then rests at the default.
  Future<void> setSplitFraction(double next) async {
    if (!next.isFinite || next < kSplitFractionMin || next > kSplitFractionMax) {
      return;
    }
    if ((next - splitFraction).abs() < 0.0005) return;
    splitFraction = next;
    await _saveDouble(splitKey, next);
  }

  Future<void> setPage(WebPage next) async {
    if (next == page) return;
    page = next;
    notifyListeners();
    try {
      final p = await SharedPreferences.getInstance();
      await p.setString(pageKey, next.name);
    } catch (_) {}
  }

  @visibleForTesting
  void resetForTests() {
    sentencePx = kSentencePxDefault;
    splitFraction = kSplitFractionDefault;
    page = WebPage.app;
    _loading = null;
  }
}
