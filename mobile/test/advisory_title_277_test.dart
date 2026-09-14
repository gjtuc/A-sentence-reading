import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/pdf/advisory_title.dart';

void main() {
  group('design/277 font similarity join', () {
    test('joins adjacent same-size wrap lines', () {
      final lines = [
        const PdfHeadStyledLine(
          text: 'Research Article pubs.acs.org/acscatalysis',
          sizePt: 9,
          bold: false,
          y: 10,
        ),
        const PdfHeadStyledLine(
          text: 'Revealing the Mechanism of Multiwalled Carbon',
          sizePt: 14,
          bold: true,
          y: 40,
        ),
        const PdfHeadStyledLine(
          text: 'Nanotube Growth on Supported Nickel Nanoparticles',
          sizePt: 14,
          bold: true,
          y: 56,
        ),
        const PdfHeadStyledLine(
          text: 'by in Situ Synchrotron X-ray Diffraction',
          sizePt: 14.2,
          bold: true,
          y: 72,
        ),
        const PdfHeadStyledLine(
          text: 'Albert Gili,*,† Lukas Schlicker,† and Friends*',
          sizePt: 10,
          bold: false,
          y: 100,
        ),
      ];
      final j = joinTitleByFontSimilarity(lines)!;
      expect(j.joinedN, 3);
      expect(j.title.toLowerCase(), contains('nanotube growth'));
      expect(j.title.toLowerCase(), contains('diffraction'));
      expect(j.title.toLowerCase(), isNot(contains('albert')));
    });

    test('stops at body-size neighbor', () {
      final lines = [
        const PdfHeadStyledLine(
          text: 'Reliable Element-Specific d-Band Analysis of Transition Metal',
          sizePt: 16,
          bold: true,
          y: 20,
        ),
        const PdfHeadStyledLine(
          text: 'Nanoparticles Using X-ray Absorption Spectroscopy',
          sizePt: 16,
          bold: true,
          y: 36,
        ),
        const PdfHeadStyledLine(
          text:
              'Abstract Metal nanoparticles are widely used in catalysis and sensing applications.',
          sizePt: 10,
          bold: false,
          y: 80,
        ),
      ];
      final j = joinTitleByFontSimilarity(lines)!;
      expect(j.joinedN, 2);
      expect(j.title.toLowerCase(), contains('nanoparticles using'));
      expect(j.title.toLowerCase(), isNot(contains('abstract')));
    });

    test('guess uses style_join when styled lines present', () {
      final g = guessAdvisoryTitle(
        infoTitle: '',
        headText: 'ignored plain\n',
        displayName: 'x.pdf',
        styledLines: const [
          PdfHeadStyledLine(
            text: 'Optimizing the Ni/Cu Ratio in Ni-Cu Nanoparticle Catalysts for',
            sizePt: 15,
            bold: true,
            y: 30,
          ),
          PdfHeadStyledLine(
            text: 'Methane Dry Reforming',
            sizePt: 15,
            bold: true,
            y: 46,
          ),
        ],
      );
      expect(g.styleSource, 'style_join');
      expect(g.title.toLowerCase(), contains('methane dry reforming'));
      expect(g.joinedN, 2);
    });

    test('keeps mixed-size line (sup/sub) without dropping', () {
      final lines = [
        const PdfHeadStyledLine(
          text: 'BaZr0.9Y0.1O3-δ Grain Boundary Conductivity Study',
          sizePt: 14,
          bold: true,
          y: 20,
          mixedSize: true,
        ),
      ];
      final j = joinTitleByFontSimilarity(lines)!;
      expect(j.mixedSizeLine, 1);
      expect(j.title, contains('BaZr'));
    });
  });
}
