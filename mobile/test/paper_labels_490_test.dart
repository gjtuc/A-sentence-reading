import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/paper_models.dart';
import 'package:sentence_reading/api/voice_ask_models.dart';
import 'package:sentence_reading/services/paper_disk_store.dart';
import 'package:sentence_reading/services/shadow_mic.dart';
import 'package:sentence_reading/state/paper_labels.dart';
import 'package:sentence_reading/widgets/paper_label_dialogs.dart';
import 'package:sentence_reading/widgets/voice_ask_overlay.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _title = 'Nickel copper alloy methane dry reforming study title';

class _FakeMic implements ShadowMic {
  final List<String> calls = [];

  @override
  Future<bool> ensurePermission() async => true;

  @override
  Future<bool> prepare(String tag) async => true;

  @override
  Future<bool> start(String tag, {bool usePrimed = true}) async {
    calls.add('start:$tag');
    return true;
  }

  @override
  Future<MicTake?> stop() async =>
      MicTake(bytes: Uint8List.fromList(const [1, 2, 3]), mime: 'audio/webm');

  @override
  Future<void> cancel() async {}

  @override
  Future<double> level() async => 0.5;

  @override
  void dispose() {}
}

class _FakeTransport implements PaperLabelTransport {
  Map<String, Map<String, dynamic>> remote = {};
  final List<Map<String, Object?>> sent = [];

  @override
  Future<Map<String, Map<String, dynamic>>> all() async => remote;

  @override
  Future<void> put(String cacheId, Map<String, Object?> label) async =>
      sent.add({'id': cacheId, ...label});
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('design/490 titles fold to one line of at most 300 characters', () {
    expect(cleanPaperLabelTitle('  A \n\t B  '), 'A B');
    expect(cleanPaperLabelTitle('x' * 400).length, kPaperLabelTitleMax);
  });

  test('design/490 a label is kept, sent, and cleared', () async {
    final t = _FakeTransport();
    var now = DateTime.utc(2026, 10, 30, 10);
    final store = PaperLabelStore(
      transport: t,
      deviceId: () async => 'phoneDEV0000000001',
      clock: () => now,
    );
    await store.bindUid('u1');
    await store.set('abc', title: '니켈 정리', kind: 'review');
    expect(store.labelFor('abc')?.title, '니켈 정리');
    expect(store.labelFor('abc')?.kind, 'review');
    expect(t.sent.single['t'], '니켈 정리');

    now = now.add(const Duration(minutes: 1));
    await store.set('abc');
    expect(store.labelFor('abc'), isNull);
    expect(t.sent.last.containsKey('t'), isFalse);

    final again = PaperLabelStore(transport: t, deviceId: () async => 'd');
    await again.bindUid('u1');
    expect(again.labelFor('abc'), isNull);
  });

  test('design/490 a newer label from the server wins, an older one does not', () async {
    final t = _FakeTransport();
    final store = PaperLabelStore(
      transport: t,
      deviceId: () async => 'phoneDEV0000000001',
      clock: () => DateTime.utc(2026, 10, 30, 10),
    );
    await store.bindUid('u1');
    await store.set('abc', title: 'Mine');
    t.remote = {
      'abc': {'at': '2026-10-30T09:00:00Z', 'dev': 'w', 't': 'Old'},
      'def': {'at': '2026-10-30T11:00:00Z', 'dev': 'w', 'k': 'general'},
    };
    await store.pull();
    expect(store.labelFor('abc')?.title, 'Mine');
    expect(store.labelFor('def')?.kind, 'general');
  });

  test('design/490 the card shows the reader title and kind over the analysis', () {
    final e = PaperEntry(id: 'a', title: _title, libraryTag: '심사 기록', docKind: 'review');
    expect(e.shownTitle, _title);
    expect(e.shownTag, '심사 기록');
    final mine = e.copyWith(displayTitle: '내 제목', labelKind: 'paper');
    expect(mine.shownTitle, '내 제목');
    expect(mine.title, _title);
    expect(mine.effectiveKind, 'paper');
    expect(mine.shownTag, '메인');
    expect(e.copyWith(labelKind: 'general').shownTag, '일반 글');
  });

  test('design/490 a kind the reader set takes part in pairing', () {
    final main = PaperEntry(id: 'a', title: _title, labelKind: 'review');
    final si = PaperEntry(id: 'b', title: _title, docRole: 'supplementary');
    final out = applyLocalPairingPassDetailed([main, si]).papers;
    expect(out.every((e) => e.pairedCacheId.isEmpty), isTrue);
    final back = PaperEntry(id: 'a', title: _title, docKind: 'review', labelKind: 'paper');
    expect(applyLocalPairingPassDetailed([back, si]).papers.first.pairedCacheId, 'b');
  });

  Widget host(Future<void> Function(BuildContext) open) => MaterialApp(
        home: Builder(
          builder: (ctx) => Scaffold(
            body: Center(
              child: TextButton(onPressed: () => open(ctx), child: const Text('open')),
            ),
          ),
        ),
      );

  testWidgets('design/490 the title dialog saves a typed title and can go back', (tester) async {
    String? got;
    final e = PaperEntry(id: 'a', title: _title, displayTitle: '내 제목');
    await tester.pumpWidget(host((ctx) async {
      got = await showPaperTitleDialog(ctx, entry: e);
    }));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(find.text('내 제목'), findsOneWidget);
    expect(find.byKey(const ValueKey('paper_title_mic')), findsNothing);
    await tester.tap(find.byKey(const ValueKey('paper_title_reset')));
    await tester.pump();
    expect(find.byKey(const ValueKey('paper_title_reset')), findsNothing);
    await tester.enterText(find.byKey(const ValueKey('paper_title_field')), '  새   제목 ');
    await tester.tap(find.byKey(const ValueKey('paper_title_save')));
    await tester.pumpAndSettle();
    expect(got, '새 제목');
  });

  testWidgets('design/490 a spoken title replaces the field', (tester) async {
    final mic = _FakeMic();
    final seen = <String>[];
    final e = PaperEntry(id: 'a', title: _title);
    await tester.pumpWidget(host((ctx) async {
      await showPaperTitleDialog(
        ctx,
        entry: e,
        voice: (current) => VoiceAskSource(
          sentence: current,
          newMic: () => mic,
          listeningText: kTitleVoiceListening,
          tapToEndText: kTitleVoiceTapToEnd,
          transcribe: (take, sentence) async {
            seen.add(sentence);
            return const VoiceAskHeard('니켈 구리 촉매 정리');
          },
        ),
      );
    }));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('paper_title_mic')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.textContaining(kTitleVoiceListening), findsOneWidget);
    await tester.tapAt(const Offset(40, 300));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(seen, [_title]);
    expect(find.text('니켈 구리 촉매 정리'), findsOneWidget);
    expect(find.text(_title), findsNothing);
  });

  testWidgets('design/490 the kind dialog marks the analysed kind', (tester) async {
    String? got;
    final e = PaperEntry(id: 'a', title: _title, docKind: 'review');
    await tester.pumpWidget(host((ctx) async {
      got = await showPaperKindDialog(ctx, entry: e);
    }));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(find.text('자동 판단'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('paper_kind_paper')));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('paper_kind_save')));
    await tester.pumpAndSettle();
    expect(got, 'paper');
  });
}
