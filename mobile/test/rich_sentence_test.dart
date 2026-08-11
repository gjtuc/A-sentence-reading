import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/rich_sentence.dart';

void main() {
  const base = TextStyle(fontSize: 16);

  test('plain has single TextSpan', () {
    final spans = buildRichSpans('Hello Ni', base);
    expect(spans.length, 1);
    expect((spans.first as TextSpan).text, 'Hello Ni');
  });

  test('sub renders without raw tags in plain extract', () {
    expect(plainFromRichHtml('H<sub>2</sub>O'), 'H2O');
    expect(looksLikeRichHtml('H<sub>2</sub>O'), isTrue);
  });

  test('escaped entities decode for display path', () {
    final raw = 'H&lt;sub&gt;2&lt;/sub&gt;O';
    expect(unescapeRichEntities(raw), 'H<sub>2</sub>O');
    expect(plainFromRichHtml(raw), 'H2O');
  });

  test('nested italic + sub builds spans', () {
    final spans = buildRichSpans('<i>σ</i><sub>x</sub>', base);
    expect(spans, isNotEmpty);
    expect(plainFromRichHtml('<i>σ</i><sub>x</sub>'), 'σx');
  });

  test('unknown tags dropped', () {
    expect(plainFromRichHtml('a<script>x</script>b'), 'axb');
  });
}
