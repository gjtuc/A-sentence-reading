import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/pdf/advisory_title.dart';
import 'package:sentence_reading/pdf/normalize_pairing_key.dart';

void main() {
  group('design/265 title quality', () {
    test('truncated Info.Title falls through to head', () {
      final g = guessAdvisoryTitle(
        infoTitle:
            'Synchrotron X-ray Absorption and Density Functional The',
        headText:
            'Synchrotron X-ray Absorption and Density Functional Theory '
            'Study of Nickel Catalysts\n',
        displayName: 'nanotube.pdf',
      );
      expect(g.source, 'head_line');
      expect(g.title.toLowerCase(), contains('theory'));
      expect(g.title.toLowerCase().endsWith(' the'), isFalse);
    });

    test('ACS code-like Info is rejected', () {
      final g = guessAdvisoryTitle(
        infoTitle: 'am2c04149 1 2 3 4 5 6 7 8 9',
        headText:
            'Supporting Information\n'
            'University of Example\n'
            'Figure S1 XRD patterns\n'
            'Nickel copper alloy for methane dry reforming catalysts\n',
        displayName: 'am2c04149.pdf',
      );
      expect(g.source, 'head_line');
      expect(g.title.toLowerCase(), contains('nickel copper'));
    });

    test('SI caption lines skipped before title', () {
      final g = guessAdvisoryTitle(
        infoTitle: '',
        headText:
            'Supporting Information\n'
            'Department of Chemistry, Example University\n'
            'Figure S2 TEM images of catalysts\n'
            'Selective hydrogenation of acetylene over NiCu catalysts\n',
        displayName: 'an1c00673_si_001.pdf',
      );
      expect(g.source, 'head_line');
      expect(g.title.toLowerCase(), contains('hydrogenation'));
    });

    test('low-quality numeric stem yields failed', () {
      final g = guessAdvisoryTitle(
        infoTitle: '',
        headText: 'S-1\n',
        displayName: '차완_논문__1.pdf',
      );
      expect(g.source, 'failed');
      expect(g.title, isEmpty);
    });

    test('cite suffix stripped', () {
      final g = guessAdvisoryTitle(
        infoTitle: '',
        headText:
            'Operando characterisation of working catalysts '
            'To cite this article: Smith et al 2024\n',
        displayName: 'iop.pdf',
      );
      expect(g.title.toLowerCase(), contains('operando'));
      expect(g.title.toLowerCase(), isNot(contains('to cite')));
    });
  });

  group('design/265 pairing', () {
    test('isUsablePairingKey rejects short stems', () {
      expect(isUsablePairingKey('1'), isFalse);
      expect(isUsablePairingKey('2'), isFalse);
      expect(isUsablePairingKey(normalizePairingKey('1')), isFalse);
    });

    test('acsManuscriptIdFromDisplayName extracts shared id', () {
      expect(
        acsManuscriptIdFromDisplayName('an1c00673.pdf'),
        'an1c00673',
      );
      expect(
        acsManuscriptIdFromDisplayName('an1c00673_si_001.pdf'),
        'an1c00673',
      );
    });

    test('doiPairingKey normalizes', () {
      expect(
        doiPairingKey('https://doi.org/10.1021/acscatal.1c00673'),
        'doi:10.1021/acscatal.1c00673',
      );
    });
  });
}
