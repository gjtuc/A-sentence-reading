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
  });
}
