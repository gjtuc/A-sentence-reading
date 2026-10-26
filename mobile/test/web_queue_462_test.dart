import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/web_blob_store.dart';
import 'package:sentence_reading/platform/file_drop_rules.dart';
import 'package:sentence_reading/platform/saf_tree_channel.dart';
import 'package:sentence_reading/screens/pdf_import_screen.dart';

void main() {
  test('off the web there is no browser store or file dialog', () async {
    expect(await webBlobPut('web/ingest_reserve/x.pdf', [1, 2, 3]), isFalse);
    expect(await webBlobGet('web/ingest_reserve/x.pdf'), isNull);
    expect(await SafTreeChannel().pickWebDocs(downloads: true), isNull);
  });

  test('notes say how to recover', () {
    expect(kOldWordNote, contains('.docx'));
    expect(kWebBlockedFolderNote, contains('다운로드'));
    expect(kWebBlockedFolderNote, contains('안의'));
  });
}
