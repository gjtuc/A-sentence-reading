/// The title card token must name a skip instead of claiming the card matched.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/reading_models.dart';
import 'package:sentence_reading/api/title_card.dart';

const String kPaper =
    'Evaluation of calcium doped Ba-Co-Nb-O perovskite as cathode materials '
    'for intermediate-temperature solid oxide fuel cells';

const String kChrome =
    'TongYuan Xu, Chao Huang, Liping Sun *, Lihua Huo, Hui Zhao '
    'ARTICLE INFO ABSTRACT Keywords: Solid oxide fuel cells';

void main() {
  test('a publisher file id title reports the skip, not kept', () {
    final token = titleCardToken(
      [SentenceView(id: 't', text: kChrome, section: 'title')],
      '1-s2.0-S0960148125003246-mmc1',
    );
    expect(token, 'skipped_unusable');
  });

  test('no title section stays absent', () {
    final token = titleCardToken(
      [SentenceView(id: 'a', text: 'The cathode is stable.', section: 'abstract')],
      '1-s2.0-S0960148125003246-mmc1',
    );
    expect(token, 'absent');
  });

  test('a usable title still reports kept and replaced', () {
    expect(
      titleCardToken(
        [SentenceView(id: 't', text: kPaper, section: 'title')],
        kPaper,
      ),
      'kept',
    );
    expect(
      titleCardToken(
        [SentenceView(id: 't', text: kChrome, section: 'title')],
        kPaper,
      ),
      'replaced',
    );
  });
}
