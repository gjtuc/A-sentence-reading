import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/shadowing_chunk_plan.dart';

void main() {
  group('shadowingChunksForSentence', () {
    test('uses plan chunks when present', () {
      final plan = {
        'status': 'ok',
        'sentences': {
          's1': {
            'chunks': ['a', 'b'],
          },
        },
      };
      expect(
        shadowingChunksForSentence(plan, 's1', 'fallback'),
        ['a', 'b'],
      );
    });

    test('falls back to plain only when allowPlainFallback', () {
      expect(
        shadowingChunksForSentence({'status': 'ok', 'sentences': {}}, 'x', 'Hi'),
        isEmpty,
      );
      expect(
        shadowingChunksForSentence(
          {'status': 'ok', 'sentences': {}},
          'x',
          'Hi',
          allowPlainFallback: true,
        ),
        ['Hi'],
      );
    });

    test('empty when no plan chunks and blank plain', () {
      expect(
        shadowingChunksForSentence(
          {
            'status': 'ok',
            'sentences': {
              's1': {'chunks': <String>[]},
            },
          },
          's1',
          '   ',
        ),
        isEmpty,
      );
    });
  });

  group('shadowingSkipEmptyDelta', () {
    final plan = {
      'status': 'ok',
      'sentences': {
        '0': {'chunks': <String>[]},
        '1': {'chunks': <String>[]},
        '2': {
          'chunks': ['ok'],
        },
      },
    };
    final rows = <({String id, String text})>[
      (id: '0', text: ''),
      (id: '1', text: ''),
      (id: '2', text: 'x'),
    ];

    test('returns 0 when current is playable', () {
      expect(
        shadowingSkipEmptyDelta(plan: plan, sentences: rows, fromIndex: 2),
        0,
      );
    });

    test('skips empty rows to next playable', () {
      expect(
        shadowingSkipEmptyDelta(plan: plan, sentences: rows, fromIndex: 0),
        2,
      );
    });

    test('returns -1 when nothing playable remains', () {
      expect(
        shadowingSkipEmptyDelta(
          plan: plan,
          sentences: [
            (id: '0', text: ''),
            (id: '1', text: ''),
          ],
          fromIndex: 0,
        ),
        -1,
      );
    });
  });

  test('prior payload keeps only sentences that already have chunks', () {
    final prior = shadowingPriorSentences({
      'status': 'error',
      'sentences': {
        'a': {'text': 'saved line', 'chunks': ['saved', 'saved line']},
        'b': {'text': 'empty', 'chunks': []},
      },
    });
    expect(prior, {
      'a': {
        'text': 'saved line',
        'chunks': ['saved', 'saved line'],
      },
    });
  });

  test('merge keeps a saved sentence when the next response has none', () {
    final merged = mergeShadowingPlans(
      {
        'status': 'pending',
        'sentences': {
          'a': {'text': 'saved line', 'chunks': ['saved line']},
        },
      },
      {
        'status': 'error',
        'sentences': <String, dynamic>{},
      },
    );
    expect(merged['status'], 'error');
    expect(shadowingPriorSentences(merged)?['a'], isNotNull);
  });

  test('saved plan must still contain the sentence just written', () {
    const expected = {
      'status': 'pending',
      'sentences': {
        'a': {'text': 'done line', 'chunks': ['done', 'done line']},
      },
    };
    expect(shadowingPlanRetainsSentences(expected, expected), isTrue);
    expect(
      shadowingPlanRetainsSentences(
        {
          'status': 'pending',
          'sentences': {
            'a': {'text': 'done line', 'chunks': ['done']},
          },
        },
        expected,
      ),
      isFalse,
    );
  });
}
