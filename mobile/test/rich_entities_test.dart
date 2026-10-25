import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/clause_breaks.dart';
import 'package:sentence_reading/api/rich_sentence.dart';

String _spansText(List<InlineSpan> spans) {
  final b = StringBuffer();
  for (final s in spans) {
    if (s is TextSpan) {
      b.write(s.toPlainText());
    } else if (s is WidgetSpan) {
      final t = (s.child as Transform).child as Text;
      b.write(t.data);
    }
  }
  return b.toString();
}

const _order = 'Pt<sub>75</sub>Co<sub>25</sub>/C(500) &gt; '
    'Pt<sub>80</sub>Co<sub>20</sub>/C(500) &gt; Pt/C(500).';

void main() {
  const style = TextStyle(fontSize: 16);

  test('design/447 a printed > between tags shows as >', () {
    final text = _spansText(buildRichSpans(_order, style));
    expect(text, 'Pt75Co25/C(500) > Pt80Co20/C(500) > Pt/C(500).');
  });

  test('design/447 the plain text decodes each entity to one character', () {
    expect(plainFromRichHtml(_order), 'Pt75Co25/C(500) > Pt80Co20/C(500) > Pt/C(500).');
    expect(plainFromRichHtml('a &lt;600 &#176;C &amp; b'), 'a <600 °C & b');
  });

  test('design/447 a decoded < never opens a tag', () {
    const raw = 'x &lt;b&gt; y<sub>2</sub> &lt;sub&gt;';
    expect(_spansText(buildRichSpans('x &lt;b&gt; y<sub>2</sub>', style)), 'x <b> y2');
    expect(plainFromRichHtml(raw), isNot(contains('&')));
  });

  test('design/447 highlights read the decoded text', () {
    final spans = buildAnnotatedSpans(_order, style, plainMetrics: true);
    expect(_spansText(spans), plainFromRichHtml(_order));
  });

  test('design/447 clause breaks after an entity land on the same space', () {
    const raw = 'The E<sub>1/2</sub> values of the alloys decreased in the order '
        'Pt<sub>75</sub>Co<sub>25</sub> &gt; Pt<sub>80</sub>Co<sub>20</sub> &gt; Pt/C, '
        'which indicates that the activity strongly depends on the compositions '
        'of the alloy catalysts.';
    final plain = plainFromRichHtml(raw);
    final breaks = clauseBreakOffsets(plain);
    expect(breaks, isNotEmpty);
    final broken = richWithClauseBreaks(raw);
    final shown = decodeTextEntities(broken.replaceAll(RegExp(r'</?sub>'), ''));
    expect(shown, withClauseBreaks(plain, breaks));
  });
}
