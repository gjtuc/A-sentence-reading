import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/clause_breaks.dart';
import 'package:sentence_reading/api/rich_sentence.dart';

const _long =
    'Our route uses a vapour growth (VG) method, which has several strengths, '
    'including (i) making even particles in a very short process, '
    '(ii) giving easy control over two-metal mixtures, '
    '(iii) being simple to scale up to large batches, and '
    '(iv) holding the metal firmly on the support (Table S1, Supporting Information).';

List<String> _pieces(String s) =>
    withClauseBreaks(s, clauseBreakOffsets(s)).split('\n');

String _spanText(List<InlineSpan> spans) =>
    spans.map((s) => s is TextSpan ? s.toPlainText() : '\uFFFC').join();

void main() {
  test('a long sentence breaks after which and before each list mark', () {
    expect(_pieces(_long), [
      'Our route uses a vapour growth (VG) method,',
      'which has several strengths,',
      'including (i) making even particles in a very short process,',
      '(ii) giving easy control over two-metal mixtures,',
      '(iii) being simple to scale up to large batches, and',
      '(iv) holding the metal firmly on the support (Table S1, Supporting Information).',
    ]);
  });

  test('breaking keeps every offset: each break was a space', () {
    final b = clauseBreakOffsets(_long);
    expect(b, isNotEmpty);
    expect(b.every((i) => _long[i] == ' '), isTrue);
    expect(withClauseBreaks(_long, b).length, _long.length);
  });

  test('a short sentence is left whole', () {
    const s = 'The film was dried, which took an hour, and then weighed.';
    expect(clauseBreakOffsets(s), isEmpty);
  });

  test('panel marks named in passing are not a list', () {
    const s = 'The lattice spacing grows with the cobalt fraction as shown in '
        '(a) and (b) for the two samples annealed at the higher of the two '
        'temperatures used in this work.';
    expect(clauseBreakOffsets(s), isEmpty);
  });

  test('nothing breaks inside brackets', () {
    const s = 'The activity was measured in acid (0.1 M, which is the usual '
        'choice, including for the reference samples, at room temperature) '
        'and compared against the commercial catalyst over many cycles.';
    expect(clauseBreakOffsets(s), isEmpty);
  });

  test('a semicolon breaks, a piece too short to stand does not', () {
    const s = 'The mass activity rose by a factor of four over the reference '
        'catalyst; the specific activity, which we also measured, rose by a '
        'factor of three across the same potential window.';
    final p = _pieces(s);
    expect(p.first.endsWith('reference catalyst;'), isTrue);
    expect(p.length, 2);
  });

  test('the rich path keeps italics and puts the breaks in the same places', () {
    final raw = _long.replaceFirst('vapour growth', '<i>vapour growth</i>');
    final spans = buildAnnotatedSpans(
      raw,
      const TextStyle(),
      clauseBreaks: true,
    );
    expect(
      spans.whereType<TextSpan>().any((s) => s.style?.fontStyle == FontStyle.italic),
      isTrue,
    );
    expect(_spanText(spans), withClauseBreaks(_long, clauseBreakOffsets(_long)));
  });

  test('the highlight path breaks at the same offsets', () {
    final spans = buildAnnotatedSpans(
      _long,
      const TextStyle(),
      ranges: const [
        AnnotationRange(start: 4, end: 9, background: Colors.yellow),
      ],
      clauseBreaks: true,
    );
    expect(_spanText(spans), withClauseBreaks(_long, clauseBreakOffsets(_long)));
  });

  test('switched off, the sentence is unchanged', () {
    final spans = buildAnnotatedSpans(_long, const TextStyle());
    expect(_spanText(spans), _long);
  });
}
