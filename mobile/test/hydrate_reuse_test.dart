import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/hydrate_reuse.dart';
import 'package:sentence_reading/api/reading_models.dart';
import 'package:sentence_reading/api/title_card.dart';

void main() {
  test('merged library row refuses pre-merge hydrate', () {
    expect(
      shouldReuseHydrateSession(
        sideValid: true,
        sideSentenceCount: 236,
        sideFigureCount: 14,
        sideHasImage: true,
        sideSupplementaryMerged: false,
        hydrateActive: false,
        entrySentenceCount: 248,
        entryFigureCount: 22,
        entryRole: 'merged',
      ),
      isFalse,
    );
  });

  test('matching open still reuses hydrate', () {
    expect(
      shouldReuseHydrateSession(
        sideValid: true,
        sideSentenceCount: 236,
        sideFigureCount: 14,
        sideHasImage: true,
        sideSupplementaryMerged: false,
        hydrateActive: false,
        entrySentenceCount: 236,
        entryFigureCount: 14,
        entryRole: 'main',
      ),
      isTrue,
    );
  });

  test('open aligns chrome title card to session title', () {
    const paper =
        'Evaluation of calcium doped Ba-Co-Nb-O perovskite as cathode materials '
        'for intermediate-temperature solid oxide fuel cells';
    final session = ReadingSession.fromOpenJson(
      {
        'title': paper,
        'sentences': [
          {
            'id': 't',
            'section': 'title',
            'text':
                'TongYuan Xu, Chao Huang, Liping Sun * ARTICLE INFO Keywords: fuel cells',
            'text_ko': '저자 덩어리',
          },
          {
            'id': 'a',
            'section': 'abstract',
            'text': 'The cathode is stable.',
            'text_ko': '안정하다.',
          },
        ],
      },
      fallbackTitle: paper,
    );
    expect(titleCardToken(session.sentences, paper), 'kept');
    expect(session.sentences.first.text, paper);
    expect(session.sentences.first.textKo, isEmpty);
    expect(session.sentences[1].textKo, '안정하다.');
  });
}
