/// design/411 — web reader text size and line width, after Word's Immersive Reader.
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

class WebReadingStyle {
  const WebReadingStyle({
    required this.fontSize,
    required this.maxWidth,
    this.lineHeight = kWebLineHeight,
  });

  final double fontSize;
  final double maxWidth;
  final double lineHeight;
}

WebReadingStyle? webReadingStyle({
  required bool web,
  required double width,
  WebTextSize size = WebTextSize.large,
  WebColumnWidth column = WebColumnWidth.medium,
}) {
  if (!web || !width.isFinite || width < kWebReadingMinWidth) return null;
  final font = math.min(kWebTextPx[size]!, width / 18);
  final maxWidth = math.min(font * kWebColumnEm[column]!, width - 32);
  return WebReadingStyle(fontSize: font, maxWidth: maxWidth);
}

TextStyle webSentenceStyle(WebReadingStyle? web, TextStyle base) => web == null
    ? base
    : base.copyWith(fontSize: web.fontSize, height: web.lineHeight, letterSpacing: 0.2);

TextStyle webKoStyle(WebReadingStyle? web, TextStyle base) => web == null
    ? base
    : base.copyWith(fontSize: web.fontSize * 0.72, height: web.lineHeight);

/// Centres [child] in the web column; returns [child] untouched on the phone.
Widget webReadingColumn(WebReadingStyle? web, Widget child) {
  if (web == null) return child;
  return Align(
    alignment: Alignment.topCenter,
    child: ConstrainedBox(
      constraints: BoxConstraints(maxWidth: web.maxWidth),
      child: Padding(
        padding: const EdgeInsets.only(top: 24, bottom: 24),
        child: child,
      ),
    ),
  );
}

/// Rebuilds with the style for the width it gets and the current prefs.
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
            size: prefs.size,
            column: prefs.column,
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

  WebTextSize size = WebTextSize.large;
  WebColumnWidth column = WebColumnWidth.medium;
  Future<void>? _loading;

  Future<void> load() => _loading ??= _load();

  Future<void> _load() async {
    try {
      final p = await SharedPreferences.getInstance();
      size = WebTextSize.values.asNameMap()[p.getString(sizeKey) ?? ''] ?? size;
      column = WebColumnWidth.values.asNameMap()[p.getString(columnKey) ?? ''] ?? column;
      notifyListeners();
    } catch (_) {}
  }

  Future<void> setSize(WebTextSize next) async {
    if (next == size) return;
    size = next;
    notifyListeners();
    try {
      final p = await SharedPreferences.getInstance();
      await p.setString(sizeKey, next.name);
    } catch (_) {}
  }

  Future<void> setColumn(WebColumnWidth next) async {
    if (next == column) return;
    column = next;
    notifyListeners();
    try {
      final p = await SharedPreferences.getInstance();
      await p.setString(columnKey, next.name);
    } catch (_) {}
  }

  @visibleForTesting
  void resetForTests() {
    size = WebTextSize.large;
    column = WebColumnWidth.medium;
    _loading = null;
  }
}
