/// design/435 — the phone sentence size and the split the reader last left.
///
/// The web reader has its own sizes ([WebReadingPrefs]); these apply where the
/// web look is off, which is the phone.
library;

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

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

class ReaderPrefs extends ChangeNotifier {
  ReaderPrefs._();

  static final ReaderPrefs instance = ReaderPrefs._();

  static const String sentencePxKey = 'reader_sentence_px_v1';
  static const String splitKey = 'reader_split_fraction_v1';

  double sentencePx = kSentencePxDefault;
  double splitFraction = kSplitFractionDefault;
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
    notifyListeners();
    await _saveDouble(splitKey, next);
  }

  @visibleForTesting
  void resetForTests() {
    sentencePx = kSentencePxDefault;
    splitFraction = kSplitFractionDefault;
    _loading = null;
  }
}
