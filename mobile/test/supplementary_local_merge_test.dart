import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/cite_refs.dart';
import 'package:sentence_reading/services/supplementary_local_merge.dart';

void main() {
  test('orMergeReferences prefers main then si', () {
    expect(orMergeReferences([], [{'n': 1, 'text': 'a' * 40}]), isNotEmpty);
    expect(
      orMergeReferences([
        {'n': 1, 'text': 'main'}
      ], [
        {'n': 2, 'text': 'si'}
      ]),
      [
        {'n': 1, 'text': 'main'}
      ],
    );
  });

  test('rewriteSiFigureId prefixes and file rel', () {
    expect(rewriteSiFigureId('fig-0001', fallbackIndex: 1), 'si-fig-0001');
    expect(figureFileRelForId('si-fig-0001'), 'figures/si-fig-0001.png');
  });

  test('filterSiSentencesAgainstRefs drops bib dupes', () {
    final refs = [
      CiteRefEntry(
        n: 1,
        text:
            'Rakov, S.I.; Author, G.S. Journal of Materials Science 2001, 1, 1-1.',
      ),
    ];
    final kept = filterSiSentencesAgainstRefs(
      [
        {'id': 'a', 'text': 'Table S1 caption stays in practice stream here.'},
        {
          'id': 'b',
          'text':
              'Rakov, S.I.; Author, G.S. Journal of Materials Science 2001, 1, 1-1.',
        },
      ],
      refs,
    );
    expect(kept.length, 1);
    expect(kept.first['id'], 'a');
  });
}
