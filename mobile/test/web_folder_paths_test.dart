// design/416 - names for a folder connected in the browser.
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/platform/web_folder_paths.dart';

void main() {
  test('a folder key goes in and comes back out', () {
    final tree = webFolderTreeUri('d1760000000000');
    expect(tree, 'webdir:d1760000000000');
    expect(webFolderKey(tree), 'd1760000000000');
    expect(webFolderKey(' $tree '), 'd1760000000000');
    expect(webFolderKey('content://com.android.externalstorage/tree/x'), isNull);
    expect(webFolderKey('webdir:'), isNull);
    expect(webFolderKey('webdir:d1/a.pdf'), isNull);
  });

  test('a file uri splits into the folder key and the path inside it', () {
    final doc = webFolderDocUri('d1', 'papers/2024/a b.pdf');
    final parts = webFolderDocParts(doc)!;
    expect(parts.key, 'd1');
    expect(parts.path, 'papers/2024/a b.pdf');
    expect(webFolderDocParts('webdir:d1'), isNull);
    expect(webFolderDocParts('webdir:d1/'), isNull);
    expect(webFolderDocParts('webdir:/a.pdf'), isNull);
    expect(webFolderDocParts('webdir:d1/../a.pdf'), isNull);
    expect(webFolderDocParts('webdir:d1/x//a.pdf'), isNull);
    expect(webFolderDocParts('content://x/a.pdf'), isNull);
  });

  test('the same two kinds as the phone are listed', () {
    expect(webFolderListable('Paper.PDF'), isTrue);
    expect(webFolderListable('si.docx'), isTrue);
    expect(webFolderListable('notes.doc'), isFalse);
    expect(webFolderListable('scan.png'), isFalse);
  });
}
