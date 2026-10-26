import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/reading_models.dart';
import 'package:sentence_reading/api/title_card.dart';

void main() {
  const name = 'Bis(2,2,6,6-tetramethyl-3,5-heptanedionato)nickel(II)';

  test('design/466: a chemical name with locant commas is a usable title', () {
    final rows = [
      SentenceView(id: 't', text: 'heptanedionato)nickel(II)', section: 'title'),
    ];
    final out = alignTitleSentences(rows, name);
    expect(out.single.text, name);
    expect(titleCardToken(rows, name), 'replaced');
  });

  test('design/466: dropped queue files leave their name in evidence', () {
    final lib = File('lib/state/library_controller.dart').readAsStringSync();
    expect(lib, contains("reason: 'bytes_missing'"));
    expect(lib, contains("'file_name': removed.filename,"));
    expect(lib, contains("'upload_queue_wiped',"));
    final bus = File('lib/services/evidence_bus.dart').readAsStringSync();
    expect(bus, contains("key == 'file_name' ||"));
  });
}
