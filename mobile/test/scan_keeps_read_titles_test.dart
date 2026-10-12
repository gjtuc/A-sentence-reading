import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/pdf_folder_grant_models.dart';

ScannedPdfEntry _entry(PdfAdvisoryState state, {String title = ''}) =>
    ScannedPdfEntry(
      docUri: 'content://papers/a.pdf',
      displayName: 'a.pdf',
      sizeBytes: 12,
      lastModifiedMs: 34,
      advisoryTitle: title,
      advisoryState: state,
    );

void main() {
  test('design/401 an unchanged file keeps the title this run read', () {
    final prev = _entry(PdfAdvisoryState.ready, title: 'Found title');
    final kept = keptScanEntry(
      prev,
      displayName: 'a.pdf',
      sizeBytes: 12,
      lastModifiedMs: 34,
    );
    expect(identical(kept, prev), isTrue);
    expect(kept!.advisoryTitle, 'Found title');
  });

  test('design/401 a read in progress is kept so its result lands', () {
    final prev = _entry(PdfAdvisoryState.computing);
    final kept = keptScanEntry(
      prev,
      displayName: 'a.pdf',
      sizeBytes: 12,
      lastModifiedMs: 34,
    );
    expect(identical(kept, prev), isTrue);
  });

  test('design/401 a changed or unread file is read again', () {
    final ready = _entry(PdfAdvisoryState.ready, title: 'Old');
    expect(
      keptScanEntry(ready,
          displayName: 'a.pdf', sizeBytes: 13, lastModifiedMs: 34),
      isNull,
    );
    expect(
      keptScanEntry(ready,
          displayName: 'a.pdf', sizeBytes: 12, lastModifiedMs: 35),
      isNull,
    );
    expect(
      keptScanEntry(ready,
          displayName: 'b.pdf', sizeBytes: 12, lastModifiedMs: 34),
      isNull,
    );
    expect(
      keptScanEntry(_entry(PdfAdvisoryState.unknown),
          displayName: 'a.pdf', sizeBytes: 12, lastModifiedMs: 34),
      isNull,
    );
    expect(
      keptScanEntry(null,
          displayName: 'a.pdf', sizeBytes: 12, lastModifiedMs: 34),
      isNull,
    );
  });

  test('design/401 a cancelled read does not stay in progress', () {
    final mid = _entry(PdfAdvisoryState.computing);
    final done = _entry(PdfAdvisoryState.ready, title: 'Done');
    releaseAbandonedReads([mid, done]);
    expect(mid.advisoryState, PdfAdvisoryState.unknown);
    expect(done.advisoryState, PdfAdvisoryState.ready);
    expect(
      keptScanEntry(mid,
          displayName: 'a.pdf', sizeBytes: 12, lastModifiedMs: 34),
      isNull,
    );
  });
}
