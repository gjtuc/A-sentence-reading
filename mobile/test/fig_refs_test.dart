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
}
