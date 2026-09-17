import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/pdf_folder_grant_models.dart';
import 'package:sentence_reading/pdf/normalize_pairing_key.dart';

ScannedPdfEntry _entry({
  required String uri,
  required String name,
  required String title,
  required String role,
}) {
  return ScannedPdfEntry(
    docUri: uri,
    displayName: name,
    sizeBytes: 10,
    lastModifiedMs: 1,
    advisoryTitle: title,
    advisoryRole: role,
    advisoryState: PdfAdvisoryState.ready,
  );
}

void main() {
  test('displayed titles pair within five character edits', () {
    final built = buildPdfImportListItems([
      _entry(
        uri: 'content://main',
        name: 'nickel.pdf',
        title: 'Recent advances in promoting dry reforming of methane',
        role: 'main',
      ),
      _entry(
        uri: 'content://si',
        name: 'nickel-si.pdf',
        title: 'Recent advancse in promoting dry reforming of methane',
        role: 'supplementary',
      ),
    ]);
    expect(built.nSets, 1);
  });

  test('filename shown as the title does not pair', () {
    final built = buildPdfImportListItems([
      _entry(
        uri: 'content://main',
        name: '1-s2.0-S0926337311005364-main.pdf',
        title: '1-s2.0-S0926337311005364-main',
        role: 'main',
      ),
      _entry(
        uri: 'content://si',
        name: '1-s2.0-S0926337311005364-mmc1.pdf',
        title: '1-s2.0-S0926337311005364-mmc1',
        role: 'supplementary',
      ),
    ]);
    expect(built.nSets, 0);
  });

  test('pairing edit distance stops after five', () {
    expect(
      pairingKeysWithinTypos(
        'recent advances in promoting dry reforming',
        'recent advancs in promoting dry reforming',
      ),
      isTrue,
    );
    expect(
      pairingKeysWithinTypos(
        'recent advances in promoting dry reforming',
        'totally different catalyst review paper title',
      ),
      isFalse,
    );
  });
}
