import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/progress_gate.dart';

void main() {
  group('validateProgressIndices', () {
    test('accepts in-range ints', () {
      final v = validateProgressIndices(
        sentenceIndex: 2,
        figureIndex: 1,
        sentenceCount: 5,
        figureCount: 3,
      );
      expect(v.ok, isTrue);
      expect(v.sentenceIndex, 2);
      expect(v.figureIndex, 1);
    });

    test('accepts digit strings', () {
      final v = validateProgressIndices(
        sentenceIndex: '3',
        figureIndex: '0',
        sentenceCount: 5,
        figureCount: 1,
      );
      expect(v.ok, isTrue);
      expect(v.sentenceIndex, 3);
    });

    test('refuses OOB sentence', () {
      final v = validateProgressIndices(
        sentenceIndex: 9,
        figureIndex: 0,
        sentenceCount: 5,
        figureCount: 2,
      );
      expect(v.ok, isFalse);
      expect(v.error, 'sentence_out_of_range');
    });

    test('refuses OOB figure when figures exist', () {
      final v = validateProgressIndices(
        sentenceIndex: 0,
        figureIndex: 4,
        sentenceCount: 5,
        figureCount: 2,
      );
      expect(v.ok, isFalse);
      expect(v.error, 'figure_out_of_range');
    });

    test('no figures requires figure==0', () {
      expect(
        validateProgressIndices(
          sentenceIndex: 0,
          figureIndex: 0,
          sentenceCount: 3,
          figureCount: 0,
        ).ok,
        isTrue,
      );
      expect(
        validateProgressIndices(
          sentenceIndex: 0,
          figureIndex: 1,
          sentenceCount: 3,
          figureCount: 0,
        ).error,
        'figure_out_of_range',
      );
    });

    test('refuses non-integer', () {
      final v = validateProgressIndices(
        sentenceIndex: '1.5',
        figureIndex: 0,
        sentenceCount: 5,
        figureCount: 1,
      );
      expect(v.ok, isFalse);
      expect(v.error, 'non_integer_index');
    });
  });

  test('progressPrefsKey scopes uid', () {
    expect(progressPrefsKey(null), 'asr.progress.v1');
    expect(progressPrefsKey(''), 'asr.progress.v1');
    expect(progressPrefsKey('user-1'), 'asr.progress.v1.u.user-1');
  });
}
