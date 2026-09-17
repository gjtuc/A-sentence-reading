import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/pdf/advisory_title.dart';

void main() {
  test('wide box in the large-font band beats a taller narrow masthead', () {
    final g = guessAdvisoryTitle(
      infoTitle: 'Catalysis Science & Technology',
      headText: '',
      displayName: 'd3cy01612a.pdf',
      styledLines: const [
        PdfHeadStyledLine(
          text: 'Catalysis Science & Technology',
          sizePt: 21,
          bold: true,
          y: 20,
          width: 123,
        ),
        PdfHeadStyledLine(
          text: 'Recent advances in promoting dry reforming of methane',
          sizePt: 20.2,
          bold: true,
          y: 136,
          width: 357,
        ),
        PdfHeadStyledLine(
          text: 'using nickel-based catalysts',
          sizePt: 20.2,
          bold: true,
          y: 156,
          width: 210,
        ),
      ],
    );
    expect(g.styleSource, 'wide_box');
    expect(g.title.toLowerCase(), contains('dry reforming'));
    expect(g.title.toLowerCase(), contains('nickel-based'));
    expect(g.title.toLowerCase(), isNot(contains('catalysis science')));
  });
}
