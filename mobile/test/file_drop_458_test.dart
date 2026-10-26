import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/upload_limits.dart';
import 'package:sentence_reading/platform/file_drop_rules.dart';
import 'package:sentence_reading/platform/web_file_drop.dart';

void main() {
  test('design/458 only non-empty files under the cap are queued', () {
    expect(droppableDoc('paper.pdf', 1000), isTrue);
    expect(droppableDoc('Paper.PDF', 1000), isTrue);
    expect(droppableDoc('paper.pdf.txt', 1000), isFalse);
    expect(droppableDoc('empty.pdf', 0), isFalse);
    expect(droppableDoc('big.pdf', 10, maxBytes: 5), isFalse);
  });

  test('design/458 off the web the drop hook is a no-op', () {
    var calls = 0;
    final remove = installFileDrop(
      onOver: (_) => calls += 1,
      onFiles: (_, __, ___) => calls += 1,
    );
    remove();
    expect(calls, 0);
  });

  test('design/460 Word files and files up to 100MB are queued', () {
    expect(kMaxUploadBytes, 100 * 1024 * 1024);
    expect(droppableDoc('notes.docx', 1000), isTrue);
    expect(droppableDoc('Notes.DOCX', 1000), isTrue);
    expect(droppableDoc('old.doc', 1000), isFalse);
    expect(droppableDoc('big.pdf', 99 * 1024 * 1024), isTrue);
    expect(droppableDoc('big.pdf', 100 * 1024 * 1024), isTrue);
    expect(droppableDoc('big.pdf', 100 * 1024 * 1024 + 1), isFalse);
  });

  test('design/461 old Word files are told apart, not queued', () {
    expect(isOldWordDoc('paper.doc'), isTrue);
    expect(isOldWordDoc(' Paper.DOC '), isTrue);
    expect(isOldWordDoc('paper.docx'), isFalse);
    expect(isOldWordDoc('paper.pdf'), isFalse);
    expect(droppableDoc('paper.doc', 1000), isFalse);
  });
}
