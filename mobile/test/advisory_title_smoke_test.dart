import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/pdf/advisory_title.dart';
import 'package:sentence_reading/pdf/doc_role_detect.dart';

void main() {
  test('design/234·236 journal chrome regexp and rsc.li skip', () {
    expect(isAdvisoryTitleChrome('PAPER'), isTrue);
    expect(
      isAdvisoryTitleChrome('Cite this: Catal. Sci. Technol., 2024,'),
      isTrue,
    );
    expect(
      isAdvisoryTitleChrome('Journal of Physics D: Applied Physics'),
      isTrue,
    );
    expect(isAdvisoryTitleChrome('rsc.li/catalysis'), isTrue);
    final gRsc = guessAdvisoryTitle(
      infoTitle: '',
      headText: 'REVIEW\n'
          'Cite this: Catal. Sci. Technol., 2024,\n'
          'DOI: 10.1039/d3cy01612a\n'
          'rsc.li/catalysis\n'
          'Recent advances in promoting dry reforming of\n'
          'methane\n',
      displayName: 'd3cy.pdf',
    );
    expect(gRsc.source, 'head_line');
    expect(gRsc.title.toLowerCase(), contains('dry reforming'));
    expect(gRsc.title.toLowerCase(), isNot(contains('rsc.li')));
    final g = guessAdvisoryTitle(
      infoTitle: '',
      headText:
          'Journal of Physics D: Applied Physics\n'
          'In situ and operando characterisation of working catalysts\n',
      displayName: 'x.pdf',
    );
    expect(g.source, 'head_line');
    expect(g.title.toLowerCase(), contains('operando'));
    final det = detectDocRoleDetailed(
      'Supporting Information\nS-1\nTitle',
      filename: 'an1c00673_si_001.pdf',
    );
    expect(det.role, anyOf('supplementary', 'main'));

    // design/254 — HTML / XML entity decoding in advisory title
    final gMetal = guessAdvisoryTitle(
      infoTitle:
          'Metal&#x2013;support interactions in metal oxide-supported atomic, cluster, and nanoparticle catalysis',
      headText: '',
      displayName: 'd4cs00527a.pdf',
    );
    expect(gMetal.source, 'info');
    expect(
      gMetal.title,
      'Metal–support interactions in metal oxide-supported atomic, cluster, and nanoparticle catalysis',
    );
    expect(gMetal.title, isNot(contains('&#x')));

    // design/255 — Chemical Engineering Journal chrome + 209-char title
    expect(
      isAdvisoryTitleChrome('Chemical Engineering Journal 510 (2025) 161545'),
      isTrue,
    );
    expect(isAdvisoryTitleChrome('Available online 12 March 2025'), isTrue);

    final longTitle =
        'Homogeneous formation of a disordered NiAl2O4 structure in three-dimensional '
        'macroporous Ni/Al2O3 catalysts for dry reforming of methane and '
        'coke-resistant catalytic behavior on its Ni-oxygen vacancy interface';
    expect(looksLikePaperTitle(longTitle), isTrue);

    final gCej = guessAdvisoryTitle(
      infoTitle: longTitle,
      headText:
          'Chemical Engineering Journal 510 (2025) 161545\n'
          'Available online 12 March 2025\n'
          '$longTitle\n',
      displayName: '1-s2.0-S1385894725023678-main.pdf',
    );
    expect(gCej.source, 'info');
    expect(gCej.title, longTitle);

    // design/255 — Docx SI role classification
    final detDocxMmc = detectDocRoleDetailed(
      'Experimental methods and characterization details.',
      filename: '차완_논문__1-s2.0-S1385894724017960-mmc1 (2).docx',
    );
    expect(detDocxMmc.role, 'supplementary');
    expect(detDocxMmc.reason, 'filename_si_and_docx');

    final detDocxSupp = detectDocRoleDetailed(
      'Experimental methods and characterization details.',
      filename: '차완_논문__smll71948-sup-0001-suppmat.docx',
    );
    expect(detDocxSupp.role, 'supplementary');
    expect(detDocxSupp.reason, 'filename_si_and_docx');

    final detTableFig = detectDocRoleDetailed(
      'Overview.\nTable S1: Catalyst textural properties.\nFigure S1: XRD spectra.',
      filename: '1-s2.0-S1385894724017960-mmc1.pdf',
    );
    expect(detTableFig.role, 'supplementary');
    expect(detTableFig.reason, 'filename_si_and_table_fig');
  });
}
