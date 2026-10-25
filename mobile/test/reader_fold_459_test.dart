/// design/459 — a folded figure pane opens only for sentences that name a
/// figure, and a swiped sentence does not flash back before the next one.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:sentence_reading/api/client.dart';
import 'package:sentence_reading/api/reader_layout_policy.dart';
import 'package:sentence_reading/api/reading_models.dart';
import 'package:sentence_reading/api/session_store.dart';
import 'package:sentence_reading/screens/reader_screen.dart';
import 'package:sentence_reading/state/annotation_controller.dart';
import 'package:sentence_reading/state/bookmark_controller.dart';
import 'package:sentence_reading/state/cite_panel_controller.dart';
import 'package:sentence_reading/state/library_controller.dart';
import 'package:sentence_reading/state/reader_prefs.dart';
import 'package:sentence_reading/state/shadowing_controller.dart';
import 'package:sentence_reading/state/translate_controller.dart';
import 'package:sentence_reading/state/tts_controller.dart';

const _texts = [
  'As shown in Fig. 1, the film grows evenly.',
  'The growth rate stays the same at every step.',
  'Fig. 2 compares the two samples side by side.',
  'Both samples keep their shape after heating.',
  'The method also scales to larger batches easily.',
];

ReadingSession _session() => ReadingSession.fromOpenJson({
      'session_id': 'ses_fold',
      'cache_id': 'c1',
      'title': 'Fold Paper',
      'sentences': [
        for (var i = 0; i < _texts.length; i++)
          {'id': 's$i', 'text': _texts[i], 'section': 'results'},
      ],
      'figures': [
        {'id': 'f1', 'image_src': '', 'caption': 'Fig. 1 — film', 'slot_key': 'fig:1'},
        {'id': 'f2', 'image_src': '', 'caption': 'Fig. 2 — samples', 'slot_key': 'fig:2'},
      ],
      'sentence_index': 0,
      'figure_index': 0,
    });

AsrClient _client() {
  final mock = MockClient((request) async {
    final path = request.url.path;
    if (path.contains('/api/session/') && path.endsWith('/cursor')) {
      return http.Response('{"ok":true,"sentence_index":0,"figure_index":0}', 200,
          headers: {'content-type': 'application/json'});
    }
    if (path.endsWith('/api/status')) {
      return http.Response('{"ok":true,"version":"0.3.476","pipeline":"rich-v24"}', 200,
          headers: {'content-type': 'application/json'});
    }
    return http.Response('{}', 404);
  });
  return AsrClient(httpClient: mock, sessionStore: MemorySessionStore());
}

Future<void> _pump(WidgetTester tester, LibraryController library, AsrClient client) async {
  tester.view.physicalSize = const Size(411, 891);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: ReaderScreen(
        library: library,
        tts: TtsController(client: client, library: library),
        client: client,
        shadowing: ShadowingController(),
        translate: TranslateController(),
        citePanel: CitePanelController(),
        bookmarks: BookmarkController(client: client),
        annotations: AnnotationController(client: client),
      ),
    ),
  ));
  await _settle(tester);
}

/// Same as the reader widget tests: assert only on the settled layout.
Future<void> _settle(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pump(const Duration(milliseconds: 400));
}

bool _split(WidgetTester tester) => find
    .byWidgetPredicate((w) => w.runtimeType.toString() == '_SplitHandle')
    .evaluate()
    .isNotEmpty;

Finder _sentence(int i) => find.textContaining(_texts[i], findRichText: true);

Future<void> _doubleTapSentence(WidgetTester tester, int i) async {
  final detectors = tester.widgetList<GestureDetector>(
    find.ancestor(of: _sentence(i).first, matching: find.byType(GestureDetector)),
  );
  detectors.firstWhere((g) => g.onDoubleTap != null).onDoubleTap!();
  await _settle(tester);
}

Future<void> _next(WidgetTester tester, LibraryController library) async {
  library.advanceSentence(1);
  await _settle(tester);
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    ReaderPrefs.instance.resetForTests();
  });

  test('design/459 a folded pane follows only figure-naming sentences', () {
    final p = ReaderLayoutPolicy()..threshold = 0;
    p.folded = true;
    expect(
      p.desireFor(sentenceIndex: 3, sectionIsTitle: false, hasCover: false),
      ReaderLayoutDesire.sentenceOnly,
    );
    expect(
      p.desireFor(
          sentenceIndex: 3, sectionIsTitle: false, hasCover: false, namesFigure: true),
      ReaderLayoutDesire.splitDefault,
    );
    expect(
      p.desireFor(sentenceIndex: 0, sectionIsTitle: true, hasCover: true),
      ReaderLayoutDesire.sentenceOnly,
    );
    p.resetForPaper(threshold: 0, autoEnabled: true);
    expect(p.folded, isFalse);
  });

  testWidgets('design/459 folded: opens on Fig sentences, folds again after',
      (tester) async {
    final client = _client();
    final library = LibraryController(client: client)..session = _session();
    await _pump(tester, library, client);
    expect(_split(tester), isTrue);

    await _doubleTapSentence(tester, 0);
    expect(_split(tester), isFalse);

    await _next(tester, library);
    expect(library.session!.sentenceIndex, 1);
    expect(_split(tester), isFalse);

    await _next(tester, library);
    expect(_split(tester), isTrue);

    await _next(tester, library);
    expect(_split(tester), isFalse);

    // A double tap while folded unfolds for good.
    await _doubleTapSentence(tester, 3);
    expect(_split(tester), isTrue);
    await _next(tester, library);
    expect(library.session!.sentenceIndex, 4);
    expect(_split(tester), isTrue);
  });

  testWidgets('design/459 not folded: the figure pane stays', (tester) async {
    final client = _client();
    final library = LibraryController(client: client)..session = _session();
    await _pump(tester, library, client);
    for (var i = 1; i <= 3; i++) {
      await _next(tester, library);
      expect(library.session!.sentenceIndex, i);
      expect(_split(tester), isTrue);
    }
  });

  // The swipe's own next waits on the player stop, which never answers in a
  // widget test, so the sentence stays parked until the model moves.
  Future<double> flyOff(WidgetTester tester) async {
    await tester.fling(_sentence(0).first, const Offset(-300, 0), 1500);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    return tester.getTopLeft(_sentence(0).first).dx;
  }

  testWidgets('design/459 a swiped sentence waits off screen for the next one',
      (tester) async {
    final client = _client();
    final library = LibraryController(client: client)..session = _session();
    await _pump(tester, library, client);
    final width = tester.view.physicalSize.width;

    expect(await flyOff(tester), lessThan(-width / 2));
    await tester.pump(const Duration(milliseconds: 50));
    expect(tester.getTopLeft(_sentence(0).first).dx, lessThan(-width / 2));

    library.advanceSentence(1);
    await tester.pump();
    expect(_sentence(0), findsNothing);
    expect(tester.getTopLeft(_sentence(1).first).dx, inInclusiveRange(0, width / 2));
    await _settle(tester);
  });

  testWidgets('design/459 a swipe that moves nothing springs back',
      (tester) async {
    final client = _client();
    final library = LibraryController(client: client)..session = _session();
    await _pump(tester, library, client);
    final width = tester.view.physicalSize.width;

    expect(await flyOff(tester), lessThan(-width / 2));
    await tester.pump(const Duration(milliseconds: 500));
    await _settle(tester);
    expect(library.session!.sentenceIndex, 0);
    expect(tester.getTopLeft(_sentence(0).first).dx, inInclusiveRange(0, width / 2));
  });
}
