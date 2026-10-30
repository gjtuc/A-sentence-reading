import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/services/helper_store.dart';
import 'package:sentence_reading/services/near_sync.dart';

/// In-memory stand-in for scripts/helper_store.py over the /store socket.
class FakeHelper {
  final papers = <String, Map<String, Object?>>{};
  final files = <String, Uint8List>{};
  final gone = <String, int>{};
  Map<String, Object?> progress = {};
  int clock = 1000;

  var _toPage = StreamController<Object>();
  Map<String, Object?>? _pendingPut;

  HelperLine line() {
    _toPage = StreamController<Object>();
    _toPage.add(<String, Object?>{'t': 'hello', 'helper': '1', 'store': true, 'cable': false});
    return HelperLine(
      incoming: _toPage.stream,
      sendText: (t) => _onText(jsonDecode(t) as Map<String, Object?>),
      sendBinary: _onBinary,
      close: () async {},
    );
  }

  void _reply(Map<String, Object?> m) => _toPage.add(m);

  void _onBinary(Uint8List b) {
    final r = _pendingPut!;
    _pendingPut = null;
    files['${r['id']}/${r['kind']}/${r['name']}'] = b;
    _reply({'q': r['q'], 'ok': true});
  }

  void _onText(Map<String, Object?> r) {
    final q = r['q'];
    final id = '${r['id'] ?? ''}';
    switch (r['t']) {
      case 'list':
        _reply({'q': q, 'ok': true, 'papers': papers, 'gone': gone});
      case 'put_file':
        _pendingPut = r;
      case 'put_done':
        final meta = Map<String, Object?>.from(r['meta']! as Map);
        papers[id] = {...meta, 'id': id, 'saved_at': ++clock};
        gone.remove(id);
        _reply({'q': q, 'ok': true});
      case 'get_file':
        final b = files['$id/${r['kind']}/${r['name']}'];
        if (b == null) {
          _reply({'q': q, 'ok': false, 'error': 'not_found'});
        } else {
          _reply({'q': q, 'ok': true, 'size': b.length});
          _toPage.add(b);
        }
      case 'forget':
        final dropped = <String>[];
        for (final e in (r['gone']! as Map).entries) {
          final at = (e.value as num).toInt();
          if (at > (gone[e.key] ?? 0)) gone['${e.key}'] = at;
          final p = papers['${e.key}'];
          if (p != null && (p['saved_at']! as int) <= at) {
            papers.remove(e.key);
            dropped.add('${e.key}');
          }
        }
        _reply({'q': q, 'ok': true, 'dropped': dropped});
      case 'progress':
        _reply({'q': q, 'ok': true, 'rows': progress});
      case 'put_progress':
        progress = Map<String, Object?>.from(r['rows']! as Map);
        _reply({'q': q, 'ok': true});
      default:
        _reply({'q': q, 'ok': false, 'error': 'unknown'});
    }
  }
}

class FakeBrowser implements NearLocal, NearForget {
  final held = <String, NearPaper>{};
  final packs = <String, Map<String, Uint8List>>{};
  final extras = <String, Map<String, Uint8List>>{};
  final goneMap = <String, int>{};
  final hiddenIds = <String>{};
  final rows = <String, Map<String, dynamic>>{};
  final dropped = <String>[];

  void add(String id, int added) {
    held[id] = NearPaper(id: id, title: 'T $id', hash: 'h$id', added: added);
    packs[id] = {'session.json': Uint8List.fromList(utf8.encode('{"id":"$id"}'))};
    extras[id] = {'shadowing/voice/$id.m4a': Uint8List.fromList([1, 2, 3])};
  }

  @override
  Future<List<NearPaper>> papers() async => held.values.toList();
  @override
  Future<Map<String, Uint8List>> pack(String id) async => packs[id] ?? const {};
  @override
  Future<bool> store(NearPaper paper, Map<String, Uint8List> files) async {
    held[paper.id] = paper;
    packs[paper.id] = files;
    return true;
  }

  @override
  Future<Map<String, Map<String, dynamic>>> progress() async => rows;
  @override
  Future<int> mergeProgress(Map<String, Map<String, dynamic>> incoming) async {
    var n = 0;
    for (final e in incoming.entries) {
      if (!rows.containsKey(e.key)) {
        rows[e.key] = e.value;
        n += 1;
      }
    }
    return n;
  }

  @override
  Future<Map<String, List<String>>> extraNames() async => const {};
  @override
  Future<Map<String, Uint8List>> extraPack(String id, Set<String> skipNames) async =>
      extras[id] ?? const {};
  @override
  Future<int> mergeExtra(String id, Map<String, Uint8List> files) async {
    extras[id] = files;
    return files.length;
  }

  @override
  Future<Map<String, int>> gone() async => goneMap;
  @override
  Future<Set<String>> hidden() async => hiddenIds;
  @override
  Future<void> forget(Map<String, int> gone, List<String> drop) async {
    goneMap.addAll(gone);
    for (final id in drop) {
      held.remove(id);
      dropped.add(id);
    }
  }
}

Future<HelperMirrorReport> _pass(FakeHelper h, FakeBrowser b) async {
  final line = h.line();
  await line.hello();
  return HelperMirror(line: line, account: 'acct000001', local: b, forget: b).run();
}

void main() {
  test('helper 495: first pass sends every paper with its voice files', () async {
    final h = FakeHelper();
    final b = FakeBrowser()
      ..add('p1', 10)
      ..add('p2', 20)
      ..rows['p1'] = {'i': 4};
    final r = await _pass(h, b);
    expect(r.sent, 2);
    expect(h.papers.keys, containsAll(['p1', 'p2']));
    expect(h.files['p1/extra/shadowing/voice/p1.m4a'], [1, 2, 3]);
    expect(h.progress['p1'], {'i': 4});
    final again = await _pass(h, b);
    expect(again.sent, 0);
    expect(again.changedHere, isFalse);
  });

  test('helper 495: a wiped browser takes its papers and positions back', () async {
    final h = FakeHelper();
    final first = FakeBrowser()
      ..add('p1', 10)
      ..rows['p1'] = {'i': 4};
    await _pass(h, first);
    final wiped = FakeBrowser();
    final r = await _pass(h, wiped);
    expect(r.restored, 1);
    expect(r.changedHere, isTrue);
    expect(wiped.held['p1']!.title, 'T p1');
    expect(utf8.decode(wiped.packs['p1']!['session.json']!), '{"id":"p1"}');
    expect(wiped.extras['p1']!.keys, ['shadowing/voice/p1.m4a']);
    expect(wiped.rows['p1'], {'i': 4});
  });

  test('helper 495: a delete here leaves the copy and is not restored', () async {
    final h = FakeHelper();
    final b = FakeBrowser()..add('p1', 10);
    await _pass(h, b);
    b.held.remove('p1');
    b.goneMap['p1'] = h.clock + 50;
    final r = await _pass(h, b);
    expect(r.droppedThere, 1);
    expect(r.restored, 0);
    expect(h.papers, isEmpty);
    expect(h.gone['p1'], h.clock + 50);
  });

  test('helper 495: a delete in another browser reaches this one, a later copy stays', () async {
    final h = FakeHelper()..gone['p2'] = 500;
    final b = FakeBrowser()
      ..add('p2', 100)
      ..add('p3', 900);
    h.gone['p3'] = 600;
    final r = await _pass(h, b);
    expect(b.dropped, ['p2']);
    expect(b.goneMap['p2'], 500);
    expect(r.droppedHere, 1);
    expect(b.held.containsKey('p3'), isTrue);
    expect(h.papers.containsKey('p3'), isTrue);
    expect(h.gone.containsKey('p3'), isFalse);
  });

  test('helper 495: a paper waiting in the 20 s undo is neither sent nor restored', () async {
    final h = FakeHelper();
    final b = FakeBrowser()
      ..add('p1', 10)
      ..hiddenIds.add('p1');
    expect((await _pass(h, b)).sent, 0);
    final other = FakeBrowser()..add('p9', 1);
    await _pass(h, other);
    final hiding = FakeBrowser()..hiddenIds.add('p9');
    expect((await _pass(h, hiding)).restored, 0);
  });

  test('helper 495: runner waits, runs once, and once more after a change mid-pass', () async {
    var runs = 0;
    final gate = Completer<void>();
    final runner = HelperMirrorRunner(
      delay: const Duration(milliseconds: 10),
      pass: (_) async {
        runs += 1;
        if (runs == 1) await gate.future;
      },
    );
    runner
      ..kick('a')
      ..kick('b');
    await Future<void>.delayed(const Duration(milliseconds: 40));
    expect(runs, 1);
    runner
      ..kick('c')
      ..kick('d');
    gate.complete();
    await Future<void>.delayed(const Duration(milliseconds: 60));
    expect(runs, 2);
    runner.dispose();
  });

  test('helper 495: account key hides the uid and stays the same', () {
    final k = helperAccountKey('google-uid-123');
    expect(k, hasLength(32));
    expect(k, helperAccountKey(' google-uid-123 '));
    expect(k.contains('google'), isFalse);
  });

  test('helper 495: settings copy, quiet web line and library hooks', () {
    final tile = File('lib/widgets/helper_settings_tile.dart').readAsStringSync();
    expect(tile, contains("kHelperName = '논문 전송 도우미'"));
    expect(tile, contains('① 도우미를 설치하면 휴대폰과 컴퓨터 사이에서 논문을 USB 선으로 바로 옮겨 줘요.'));
    expect(tile, contains('② 브라우저 기록을 지우면 이 컴퓨터에 받아 둔 논문도 함께 지워져요. '));
    expect(tile, contains('도우미를 설치하면 브라우저 기록을 지워도 이 컴퓨터에 보관한 논문이 다시 돌아와요.'));
    expect(tile, contains("'도우미 연결됨'"));
    expect(tile, contains("'openDeveloperSettings'"));
    final settings = File('lib/screens/settings_screen.dart').readAsStringSync();
    final apk = settings.indexOf('_buildAppVersionSection(context),');
    expect(apk, greaterThan(0));
    expect(settings.indexOf('HelperSettingsTile(downloadUrl: _helperUrl)'), greaterThan(apk));
    final web = File('lib/services/helper_store_web.dart').readAsStringSync();
    expect(web, contains("contains('Firefox')"));
    expect(web, contains('if (!ask && !await _mayTryQuietly()) return null;'));
    final ctrl = File('lib/state/library_controller.dart').readAsStringSync();
    expect(ctrl, contains("_kickHelperMirror('refresh');"));
    expect(ctrl, contains("_kickHelperMirror('delete');"));
    expect(ctrl, contains("'helper_mirror_done'"));
    final kt = File('android/app/src/main/kotlin/com/gjtuc/sentence_reading/MainActivity.kt')
        .readAsStringSync();
    expect(kt, contains('Settings.Global.ADB_ENABLED'));
    expect(kt, contains('Settings.ACTION_APPLICATION_DEVELOPMENT_SETTINGS'));
  });
}
