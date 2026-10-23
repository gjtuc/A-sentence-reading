import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/pdf_folder_grant_models.dart';

ScannedPdfEntry _entry(String name, String title) => ScannedPdfEntry(
      docUri: 'content://$name',
      displayName: name,
      sizeBytes: 10,
      lastModifiedMs: 1,
      advisoryTitle: title,
    );

void main() {
  final growth = PdfImportSingleItem(
    _entry('cs9b00733.pdf', 'Revealing the Mechanism of Carbon Nanotube Growth'),
  );
  final alloy = PdfImportSingleItem(
    _entry('adma201600469.pdf', 'Low\u2010Temperature Synthesis of Pt\u2013Co Alloyed Nanoparticles'),
  );
  final set = PdfImportSetItem(
    main: _entry('acsnano.pdf', 'Graphene Oxide Membranes'),
    si: _entry('acsnano_si_001.pdf', ''),
    pairingKey: 'k',
  );
  final items = <PdfImportListItem>[growth, alloy, set];

  test('design/446 an empty box shows every row', () {
    expect(matchingSearch(items, ''), items);
    expect(matchingSearch(items, '   '), items);
  });

  test('design/446 the recognized title is searched, whatever the case', () {
    expect(matchingSearch(items, 'nanotube'), [growth]);
    expect(matchingSearch(items, 'GRAPHENE'), [set]);
  });

  test('design/446 the file name is searched', () {
    expect(matchingSearch(items, 'adma2016'), [alloy]);
  });

  test('design/446 every word must be there, in any order', () {
    expect(matchingSearch(items, 'growth carbon'), [growth]);
    expect(matchingSearch(items, 'carbon membranes'), isEmpty);
  });

  test('design/446 a set is found by its SI file name', () {
    expect(matchingSearch(items, 'si_001'), [set]);
  });

  test('design/446 a typed hyphen finds the dashes printed in titles', () {
    expect(matchingSearch(items, 'low-temperature pt-co'), [alloy]);
  });
}
