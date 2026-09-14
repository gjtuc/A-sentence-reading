import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/pdf_folder_grant_models.dart';
import 'package:sentence_reading/pdf/advisory_title.dart';
import 'package:sentence_reading/pdf/normalize_pairing_key.dart';

void main() {
  group('design/276 title quality', () {
    test('SI banner+title one line keeps mechanism title', () {
      final g = guessAdvisoryTitle(
        infoTitle: '',
        headText:
            'Supporting Information Revealing the Mechanism of Multiwalled '
            'Carbon Nanotube Growth on Supported Nickel Nanoparticles by '
            'in Situ Synchrotron X-ray Diffraction\n'
            'Advanced Light Source, Lawrence Berkeley National Laboratory\n',
        displayName: 'cs9b00733_si_001.pdf',
      );
      expect(g.source, 'head_line');
      expect(g.title.toLowerCase(), contains('revealing the mechanism'));
      expect(g.title.toLowerCase(), contains('nanotube'));
      expect(g.title.toLowerCase().startsWith('supporting'), isFalse);
    });

    test('ACS research article pubs.acs.org chrome rejected', () {
      final g = guessAdvisoryTitle(
        infoTitle:
            'Revealing the Mechanism of Multiwalled Carbon Nanotube Growth '
            'on Supported Nickel Nanoparticles by in Situ Synchrotron X-ray '
            'Diffraction, Density Functional Theory, and Molecular D',
        headText:
            'Albert Gili,*,† Lukas Schlicker,† Maged F. Bekheet\n'
            'Research Article pubs.acs.org/acscatalysis\n'
            'Revealing the Mechanism of Multiwalled Carbon Nanotube Growth '
            'on Supported Nickel Nanoparticles by in Situ Synchrotron '
            'X-ray Diffraction\n',
        displayName:
            'revealing-the-mechanism-of-multiwalled-carbon-nanotube-growth.pdf',
      );
      expect(g.source, 'head_line');
      expect(g.title.toLowerCase(), contains('revealing the mechanism'));
      expect(g.title.toLowerCase(), isNot(contains('pubs.acs.org')));
      expect(g.title.toLowerCase(), isNot(contains('research article')));
    });

    test('author line skipped for head title', () {
      final g = guessAdvisoryTitle(
        infoTitle: '',
        headText:
            'Kaihang Han, Shuo Wang, Qiying Liu,* and Fagen Wang*\n'
            'One-Pot Synthesis of Ordered Mesoporous NiCo2O4 for Methane '
            'Dry Reforming Catalysts\n',
        displayName: 'acsanm.1c00673.pdf',
      );
      expect(g.source, 'head_line');
      expect(g.title.toLowerCase(), contains('one-pot synthesis'));
      expect(g.title.toLowerCase(), isNot(contains('kaihang')));
    });

    test('single-letter Info truncation falls through', () {
      expect(
        isTruncatedInfoTitle(
          'Revealing the Mechanism of Multiwalled Carbon Nanotube Growth '
          'on Supported Nickel Nanoparticles by in Situ Synchrotron X-ray '
          'Diffraction, Density Functional Theory, and Molecular D',
        ),
        isTrue,
      );
    });
  });

  group('design/276 mate borrow', () {
    test('empty SI title borrows main when ACS keys match', () {
      final main = ScannedPdfEntry(
        docUri: 'content://main',
        displayName: 'cs9b00733.pdf',
        sizeBytes: 10,
        lastModifiedMs: 1,
        advisoryTitle:
            'Revealing the Mechanism of Multiwalled Carbon Nanotube Growth',
        advisoryRole: 'main',
        advisoryState: PdfAdvisoryState.ready,
        pairingKey: 'acs:cs9b00733',
      );
      final si = ScannedPdfEntry(
        docUri: 'content://si',
        displayName: 'cs9b00733_si_001.pdf',
        sizeBytes: 10,
        lastModifiedMs: 1,
        advisoryTitle: '',
        advisoryRole: 'supplementary',
        advisoryState: PdfAdvisoryState.ready,
        pairingKey: 'acs:cs9b00733',
      );
      final built = buildPdfImportListItems([main, si]);
      expect(built.nSets, 1);
      final set = built.items.whereType<PdfImportSetItem>().single;
      expect(set.si.advisoryTitle, contains('Revealing the Mechanism'));
      expect(isUsablePairingKey(set.pairingKey), isTrue);
    });
  });
}
