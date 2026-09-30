import 'sample_seed.dart';

/// design/364 - keeping the calibration sample row out of the library list.
///
/// The row cannot be deleted: it has no server document, so a delete would 404
/// forever and the purge worker would keep reporting the failure, and `bindUid`
/// seeds it again on every sign-in. It is also not something to choose about --
/// it exists to measure a scoring change, and the speaker has nothing to do with
/// it either way. So it is hidden always, and `/api/status` turns it back on for
/// as long as a calibration round needs it (`ASR_SAMPLE_ROW=1`).
///
/// Hiding is a view choice and nothing else. The takes live in GCS under the
/// speaker's own space, the bucket has no lifecycle rule, and no code path
/// deletes that prefix, so the audio outlives any number of hides.

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
