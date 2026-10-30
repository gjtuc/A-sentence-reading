import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/paper_models.dart';
import 'package:sentence_reading/api/reading_models.dart';
import 'package:sentence_reading/services/paper_disk_store.dart';

const _title = 'Nickel copper alloy methane dry reforming study title';

void main() {
  test('server row without a tag gets the kind tag', () {
    final e = PaperEntry.fromJson({'id': 'a', 'title': _title, 'doc_kind': 'review'});
    expect(e.docKind, 'review');
    expect(e.libraryTag, '심사 기록');
    final g = PaperEntry.fromJson({'id': 'b', 'title': _title, 'doc_kind': 'general'});
    expect(g.libraryTag, '일반 글');
    final p = PaperEntry.fromJson({'id': 'c', 'title': _title});
    expect(p.docKind, 'paper');
  });

  test('device row keeps the kind and shows its tag', () {
    final row = PaperDiskIndexEntry.fromJson(
      {'id': 'a', 'title': _title, 'doc_kind': 'general'},
    );
    expect(row.toJson()['doc_kind'], 'general');
    expect(row.toPaperEntry().libraryTag, '일반 글');
    expect(row.withAddedAt('2026-10-30T00:00:00Z').docKind, 'general');
    final si = PaperDiskIndexEntry.fromJson(
      {'id': 'b', 'title': _title, 'doc_role': 'supplementary', 'doc_kind': 'general'},
    );
    expect(si.toPaperEntry().libraryTag, isNot('일반 글'));
    final old = PaperDiskIndexEntry.fromJson({'id': 'c', 'title': _title});
    expect(old.toJson().containsKey('doc_kind'), isFalse);
    expect(old.toPaperEntry().docKind, 'paper');
  });

  test('a review is not paired with an SI of the same title', () {
    final review = PaperEntry(id: 'a', title: _title, docKind: 'review');
    final si = PaperEntry(id: 'b', title: _title, docRole: 'supplementary');
    final out = applyLocalPairingPassDetailed([review, si]).papers;
    expect(out.every((e) => e.pairedCacheId.isEmpty), isTrue);
    final paper = PaperEntry(id: 'a', title: _title);
    final paired = applyLocalPairingPassDetailed([paper, si]).papers;
    expect(paired.first.pairedCacheId, 'b');
  });

  test('session payload carries the kind to disk json', () {
    final s = ReadingSession.fromOpenJson({
      'cache_id': 'a',
      'title': _title,
      'sentences': [],
      'figures': [],
      'doc_kind': 'review',
    });
    expect(s.docKind, 'review');
    expect(readingSessionToPaperDiskJson(s)['doc_kind'], 'review');
  });
}
