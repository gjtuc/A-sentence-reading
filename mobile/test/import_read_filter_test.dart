import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/pdf_folder_grant_models.dart';

ScannedPdfEntry _entry(String uri, String hash) => ScannedPdfEntry(
      docUri: uri,
      displayName: '$uri.pdf',
      sizeBytes: 10,
      lastModifiedMs: 1,
      contentHash: hash,
    );

final _a = 'a' * 64;
final _b = 'b' * 64;
final _c = 'c' * 64;
final _d = 'd' * 64;

void main() {
  final single = PdfImportSingleItem(_entry('one', _a));
  final other = PdfImportSingleItem(_entry('two', _b));
  final set = PdfImportSetItem(
    main: _entry('main', _c),
    si: _entry('si', _d),
    pairingKey: 'k',
  );
  final items = <PdfImportListItem>[single, other, set];

  test('design/445 a row whose paper is read is hidden', () {
    expect(withoutReadDone(items, {_a}), [other, set]);
  });

  test('design/445 a set goes by its main file and leaves no stray SI row', () {
    expect(withoutReadDone(items, {_c}), [single, other]);
    expect(withoutReadDone(items, {_d}), items);
  });

  test('design/445 nothing read shows every row', () {
    expect(withoutReadDone(items, const {}), items);
  });

  test('design/445 a file whose hash is not known yet stays', () {
    final pending = PdfImportSingleItem(_entry('new', ''));
    expect(withoutReadDone([pending], {_a}), [pending]);
  });

  test('design/445 the hash matches whatever its case', () {
    final upper = PdfImportSingleItem(_entry('up', _a.toUpperCase()));
    expect(withoutReadDone([upper], {_a}), isEmpty);
  });
}
