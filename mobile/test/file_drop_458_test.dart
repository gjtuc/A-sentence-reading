import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/platform/file_drop_rules.dart';
import 'package:sentence_reading/platform/web_file_drop.dart';

void main() {
  test('design/458 only non-empty PDFs under the cap are queued', () {
    expect(droppablePdf('paper.pdf', 1000), isTrue);
    expect(droppablePdf('Paper.PDF', 1000), isTrue);
    expect(droppablePdf('notes.docx', 1000), isFalse);
    expect(droppablePdf('paper.pdf.txt', 1000), isFalse);
    expect(droppablePdf('empty.pdf', 0), isFalse);
    expect(droppablePdf('big.pdf', 51 * 1024 * 1024), isFalse);
    expect(droppablePdf('big.pdf', 10, maxBytes: 5), isFalse);
  });

  test('design/458 off the web the drop hook is a no-op', () {
    var calls = 0;
    final remove = installFileDrop(
      onOver: (_) => calls += 1,
      onFiles: (_, __) => calls += 1,
    );
    remove();
    expect(calls, 0);
  });
}
