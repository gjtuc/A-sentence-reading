import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/pdf_folder_grant_models.dart';
import 'package:sentence_reading/pdf/paper_title_key.dart';
import 'package:sentence_reading/state/library_keys.dart';
import 'package:sentence_reading/state/read_done.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _title = 'Low-Temperature Vapor Deposition Synthesis of Alloyed Nanoparticles';
final _h = 'c' * 64;

ScannedPdfEntry _e(String name, {String role = 'main', String title = _title, String hash = ''}) =>
    ScannedPdfEntry(
      docUri: 'webdir:d1/$name',
      displayName: name,
      sizeBytes: 1,
      lastModifiedMs: 1,
      contentHash: hash,
      advisoryState: PdfAdvisoryState.ready,
      advisoryRole: role,
      advisoryTitle: title,
    );

class _Keys implements LibraryKeysTransport {
  final devices = <String, Map<String, dynamic>>{};
  final puts = <Map<String, Object?>>[];

  @override
  Future<Map<String, Map<String, dynamic>>> all() async => devices;

  @override
  Future<void> put(Map<String, Object?> body) async {
    puts.add(body);
    devices['${body['dev']}'] = {'at': body['at'], 'items': body['items']};
  }
}

class _Done implements ReadDoneTransport {
  final remote = <String, Map<String, dynamic>>{};
  final puts = <String, Map<String, Object?>>{};

  @override
  Future<Map<String, Map<String, dynamic>>> all() async => remote;

  @override
  Future<void> put(String cacheId, Map<String, Object?> mark) async => puts[cacheId] = mark;
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('design/457 a title key needs a real title', () {
    expect(paperTitleKey('Introduction'), '');
    expect(paperTitleKey('Short Two'), '');
    expect(paperTitleKey(_title), 'low temperature vapor deposition synthesis of alloyed nanoparticles');
    expect(paperTitleKey('Low–Temperature Vapor Deposition: Synthesis of Alloyed Nanoparticles.'),
        paperTitleKey(_title));
  });

  test('design/457 another download of a kept or read paper is known by its title', () {
    final marks = PaperMarks(titles: {paperTitleKey(_title)});
    expect(marks.has(_e('other_copy.pdf')), isTrue);
    expect(marks.has(_e('x_si.pdf', role: 'supplementary')), isFalse, reason: 'SI goes by hash');
    expect(marks.has(_e('b.pdf', title: 'A Different Paper About Something Else Entirely')), isFalse);
    final byHash = PaperMarks(hashes: {_h});
    expect(byHash.has(_e('a.pdf', title: '', hash: _h)), isTrue);
    final set = PdfImportSetItem(
      main: _e('m.pdf'),
      si: _e('m_si.pdf', role: 'supplementary'),
      pairingKey: 'k',
    );
    expect(marks.hasSet(set), isTrue);
    final items = <PdfImportListItem>[set, PdfImportSingleItem(_e('z.pdf', title: 'Unrelated Long Title Of Another Paper Here'))];
    expect(withoutMarked(items, marks).length, 1);
  });

  test('design/457 the other devices\' lists are read, this device\'s is sent once', () async {
    final t = _Keys()
      ..devices['phoneDEV0000000001'] = {
        'at': '2026-10-26T00:00:00Z',
        'items': [
          {'c': 'p1', 'h': _h, 't': 'kept on the phone paper title'},
        ],
      }
      ..devices['webDEV000000000002'] = {
        'at': '2026-10-26T00:00:00Z',
        'items': [
          {'c': 'w1', 't': 'my own old list'},
        ],
      };
    final keys = AccountLibraryKeys(
      transport: t,
      deviceId: () async => 'webDEV000000000002',
      debounce: const Duration(hours: 1),
    );
    await keys.bindUid('u1');
    expect(keys.hashes, {_h});
    expect(keys.titles, {'kept on the phone paper title'});
    keys.publish(const [LibraryKey(cacheId: 'w2', title: 'now in the web library')]);
    await keys.flush();
    expect(t.puts.single['items'], [
      {'c': 'w2', 't': 'now in the web library'},
    ]);
    keys.publish(const [LibraryKey(cacheId: 'w2', title: 'now in the web library')]);
    await keys.flush();
    expect(t.puts.length, 1, reason: 'the same list is not sent again');
    keys.publish(const []);
    await keys.flush();
    expect(t.puts.last['items'], isEmpty, reason: 'a paper that left the library leaves the list');
    await keys.bindUid(null);
    expect(keys.hashes, isEmpty);
  });

  test('design/457 a read mark carries the title key and old marks get it filled in', () async {
    final t = _Done()
      ..remote['old1'] = {'done': true, 'at': '2026-10-20T00:00:00.000Z', 'dev': 'phoneDEV0000000001'};
    final store = ReadDoneStore(transport: t, deviceId: () async => 'webDEV000000000002');
    await store.bindUid('u1');
    expect(store.doneTitles, isEmpty);
    await store.fillTitles({'old1': 'old paper title key here'});
    expect(store.doneTitles, {'old paper title key here'});
    expect(t.puts['old1'], {
      'done': true,
      'at': '2026-10-20T00:00:00.000Z',
      'dev': 'phoneDEV0000000001',
      't': 'old paper title key here',
    });
    await store.mark('new1', done: true, title: 'new paper title key here');
    expect(t.puts['new1']!['t'], 'new paper title key here');

    final other = _Done()
      ..remote['old1'] = {
        'done': true,
        'at': '2026-10-20T00:00:00.000Z',
        'dev': 'phoneDEV0000000001',
        't': 'filled by the web',
      };
    SharedPreferences.setMockInitialValues({});
    final phone = ReadDoneStore(transport: other, deviceId: () async => 'phoneDEV0000000001');
    await phone.bindUid('u2');
    expect(phone.doneTitles, {'filled by the web'});
  });
}
