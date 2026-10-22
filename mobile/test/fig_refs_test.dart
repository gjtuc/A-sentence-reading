import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/fig_refs.dart';

void main() {
  test('parseFigRefs dedupes and keeps order', () {
    expect(
      parseFigRefs('See Fig. 2 and Figure 2 again, then Scheme 1a.'),
      ['Fig. 2', 'Scheme 1a'],
    );
  });

  test('matchFigureIndex by caption', () {
    final caps = [
      'Fig. 1. Models',
      'Fig. 5. ETEM',
      'Scheme 1. Route',
    ];
    expect(matchFigureIndex(refLabel: 'Fig. 5', captions: caps), 1);
    expect(matchFigureIndex(refLabel: 'Scheme 1', captions: caps), 2);
    // Unmatched → null (no fake chip).
    expect(matchFigureIndex(refLabel: 'Fig. 2', captions: caps), isNull);
  });

  test('hintsForSentence only matched', () {
    final hints = hintsForSentence(
      text: 'As in Fig. 5 and Fig. 9.',
      captions: ['Fig. 1. A', 'Fig. 5. B'],
    );
    expect(hints.length, 1);
    expect(hints.first.ref, 'Fig. 5');
    expect(hints.first.figureIndex, 1);
  });

  test('panel fallback Figure 6C design/164', () {
    final caps = ['Fig. 1a. A', 'Figure 6. XPS'];
    expect(
      parseFigRefs('(Figure 6C) and (Figure 6D)'),
      ['Figure 6'],
    );
    expect(matchFigureIndex(refLabel: 'Figure 6C', captions: caps), 1);
    final hints = hintsForSentence(
      text: 'see (Figure 6C) and (Figure 6D)',
      captions: caps,
    );
    expect(hints.length, 1);
    expect(hints.first.ref, 'Figure 6');
    expect(hints.first.figureIndex, 1);
    expect(matchFigureIndex(refLabel: 'Figure 1a', captions: caps), 0);
  });

  test('every number after one kind word design/439', () {
    expect(
      parseFigRefs('as in Figs. 5, 7 and 8.'),
      ['Figs. 5', 'Fig. 7', 'Fig. 8'],
    );
    expect(
      parseFigRefs('as in Figs. 5, 7, and 8.'),
      ['Figs. 5', 'Fig. 7', 'Fig. 8'],
    );
    expect(parseFigRefs('Figs. 5 and 6 show'), ['Figs. 5', 'Fig. 6']);
    expect(
      parseFigRefs('Figs. 5\u20137 show'),
      ['Figs. 5', 'Fig. 6', 'Fig. 7'],
    );
    expect(parseFigRefs('Tables 2 and 3 list'), ['Table 2', 'Table 3']);
    expect(parseFigRefs('Figs. S1 and S2'), ['Figs. S1', 'Fig. S2']);
    expect(parseFigRefs('Figs. 5a and 6b'), ['Figs. 5a', 'Fig. 6b']);
    expect(
      parseFigRefs('Figure 2 and Figure 3 and Figure 2'),
      ['Figure 2', 'Figure 3'],
    );
  });

  test('numbers that are not figures design/439', () {
    expect(parseFigRefs('In Fig. 3, 4 samples were used.'), ['Fig. 3']);
    expect(
      parseFigRefs('Table 3, the dispersion of 75\u201383% holds.'),
      ['Table 3'],
    );
    expect(parseFigRefs('Fig. 2\u2013200 nm'), ['Fig. 2']);
    expect(parseFigRefs('Fig. 2nd row'), isEmpty);
  });

  test('list chips only for figures in the paper design/439', () {
    final hints = hintsForSentence(
      text: 'shown in Figs. 5, 7 and 8 and Fig. 9.',
      captions: [
        'Fig. 1. A',
        'Fig. 5. B',
        'Fig. 6. C',
        'Fig. 7. D',
        'Fig. 8. E',
      ],
    );
    expect(hints.map((h) => h.ref).toList(), ['Figs. 5', 'Fig. 7', 'Fig. 8']);
    expect(hints.map((h) => h.figureIndex).toList(), [1, 3, 4]);
    final tables = hintsForSentence(
      text: 'Tables 2 and 3',
      captions: ['Table 1. a', 'Table 2. b', 'Table 3. c'],
    );
    expect(tables.map((h) => h.figureIndex).toList(), [1, 2]);
  });
}
