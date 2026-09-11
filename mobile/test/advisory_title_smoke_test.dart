import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/pdf/advisory_title.dart';
import 'package:sentence_reading/pdf/doc_role_detect.dart';

void main() {
  test('design/234 journal chrome regexp does not throw', () {
    expect(isAdvisoryTitleChrome('PAPER'), isTrue);
    expect(
      isAdvisoryTitleChrome('Cite this: Catal. Sci. Technol., 2024,'),
      isTrue,
    );
    expect(
      isAdvisoryTitleChrome('Journal of Physics D: Applied Physics'),
      isTrue,
    );
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
  });
}
