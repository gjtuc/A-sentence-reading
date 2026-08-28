import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/cite_refs.dart';

void main() {
  test('parseCiteNumbers bracket and sup', () {
    expect(parseCiteNumbers('Hello.[1] More.[2-3,5]'), [1, 2, 3, 5]);
    expect(parseCiteNumbers('x<sup>12</sup> y'), [12]);
    expect(parseCiteNumbers(''), isEmpty);
    expect(parseCiteNumbers('[0]'), isEmpty);
    expect(parseCiteNumbers('[99999]'), isEmpty);
  });

  test('parseCiteNumbers bracket-dollar hybrid', () {
    expect(parseCiteNumbers('dioxide [8, 9]\$1'), [8, 9, 1]);
    expect(parseCiteNumbers('CO<sub>2</sub>\$1'), [1]);
  });

  test('stripCiteMarkersForDisplay hybrid bracket-dollar', () {
    expect(
      stripCiteMarkersForDisplay('dioxide [8, 9]\$1.'),
      'dioxide.',
    );
    expect(
      stripCiteMarkersForDisplay('stable.[1,2] Rates'),
      'stable. Rates',
    );
    expect(
      stripCiteMarkersForDisplay('x<sup>12</sup> y'),
      'x y',
    );
    // chemistry cm-1 not stripped
    expect(
      stripCiteMarkersForDisplay('cm<sup>−1</sup> band'),
      contains('cm'),
    );
  });

  test('hintsForSentence matches bibliography', () {
    final bib = [
      const CiteRefEntry(n: 1, text: 'B. Liu, ChemElectroChem 2018.'),
      const CiteRefEntry(
        n: 2,
        text: 'A. Smith doi:10.1016/j.jcat.2019.01.001',
        doi: '10.1016/j.jcat.2019.01.001',
      ),
    ];
    final hints = hintsForSentence(text: 'stable.[1]', bibliography: bib);
    expect(hints.length, 1);
    expect(hints[0].n, 1);
    expect(hintsForSentence(text: 'no cites', bibliography: bib), isEmpty);
    expect(hintsForSentence(text: '[9]', bibliography: bib), isEmpty);
  });

  test('parseReferenceList', () {
    final rows = parseReferenceList([
      {'n': 2, 'text': 'Second ref', 'doi': ''},
      {'n': 1, 'text': 'First ref long enough', 'doi': '10.1/abc'},
      {'n': 0, 'text': 'bad'},
    ]);
    expect(rows.map((e) => e.n).toList(), [1, 2]);
    expect(rows[0].doi, '10.1/abc');
  });
}
