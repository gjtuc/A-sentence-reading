import 'package:shared_preferences/shared_preferences.dart';

import 'sample_seed.dart';

/// design/364 — whether the sample row is kept out of the library list.
///
/// The row cannot be deleted: it has no server document, so a delete would 404
/// forever and the purge worker would keep reporting the failure, and `bindUid`
/// seeds it again on every sign-in. Once the rounds are recorded there is still
/// a reason to want it out of the way, so hiding is the only honest answer.
///
/// Hiding is a view choice and nothing else. The recorded takes live in GCS
/// under the speaker's own space and are never touched by this, and turning the
/// switch back on brings the row back with its round progress intact.
const String kSampleHiddenPrefKey = 'asr.sample_row_hidden.v1';

/// Shown by default, because a speaker who has not recorded anything needs to
/// find it.
Future<bool> loadSampleRowHidden() async {
  try {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(kSampleHiddenPrefKey) ?? false;
  } catch (_) {
    return false;
  }
}

Future<void> saveSampleRowHidden(bool hidden) async {
  try {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(kSampleHiddenPrefKey, hidden);
  } catch (_) {
    // A preference that would not save is not worth taking the screen down for.
  }
}


/// Drop the sample row from [rows] when hidden.
///
/// A function rather than a line inside the controller, so the rule can be
/// tested without standing up the whole library.
List<T> withoutHiddenSample<T>(
  List<T> rows, {
  required bool hidden,
  required String Function(T) idOf,
}) {
  if (!hidden) return rows;
  return rows
      .where((row) => !isSampleCacheId(idOf(row)))
      .toList(growable: false);
}
