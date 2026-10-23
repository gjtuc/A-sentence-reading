/// design/63 — reader cursors are independent, verified through the widget tree.
///
/// WHY: the invariant was only covered by model-level tests, so a regression in
/// the panes (reading the wrong cursor, disabled chevrons) could ship unseen.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:sentence_reading/api/client.dart';
import 'package:sentence_reading/api/reading_models.dart';
import 'package:sentence_reading/api/reader_nav_labels.dart';
import 'package:sentence_reading/api/session_store.dart';
import 'package:sentence_reading/screens/reader_screen.dart';
import 'package:sentence_reading/state/annotation_controller.dart';
import 'package:sentence_reading/state/bookmark_controller.dart';
import 'package:sentence_reading/state/cite_panel_controller.dart';
import 'package:sentence_reading/state/library_controller.dart';
import 'package:sentence_reading/state/reader_prefs.dart';
import 'package:sentence_reading/state/web_reading_prefs.dart';
import 'package:sentence_reading/state/shadowing_controller.dart';
import 'package:sentence_reading/state/translate_controller.dart';
import 'package:sentence_reading/state/tts_controller.dart';

ReadingSession _session({
  int sentences = 3,
  int figures = 2,
  String cacheId = 'c1',
}) {
  return ReadingSession.fromOpenJson({
    'session_id': 'ses_test',
    'cache_id': cacheId,
    'title': 'Independent Cursor Paper',
    'sentences': [
      for (var i = 0; i < sentences; i++)
        {'id': 's$i', 'text': 'Sentence body number $i.', 'section': 'results'},
    ],
    'figures': [
      for (var i = 0; i < figures; i++)
        {
          'id': 'fig-$i',
          'image_src': '',
          'caption': 'Caption for figure number $i.',
          'slot_key': 'fig:$i',
        },
    ],
    'sentence_index': 0,
    'figure_index': 0,
  });
}

/// Reader under a MaterialApp with every controller wired to a mock transport.
///
/// NOTE: ReaderScreen has no Scaffold of its own — HomeShell supplies it, and
/// the ink splashes on the nav chevrons assert without a Material ancestor.
Widget _readerHarness(LibraryController library, AsrClient client) {
  return MaterialApp(
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
  );
}

AsrClient _mockClient() {
  final mock = MockClient((request) async {
    final path = request.url.path;
    // PATCH /api/session/{id}/cursor — the reader persists both cursors on move.
    if (path.contains('/api/session/') && path.endsWith('/cursor')) {
      return http.Response(
        '{"ok":true,"sentence_index":0,"figure_index":0}',
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (path.endsWith('/api/status')) {
      return http.Response(
        '{"ok":true,"version":"0.3.311","pipeline":"rich-v24"}',
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    return http.Response('{}', 404);
  });
  return AsrClient(httpClient: mock, sessionStore: MemorySessionStore());
}

/// The chevrons are IconButtons; `byTooltip` matches the Tooltip they build.
Finder _chevron(String tooltip) =>
    find.ancestor(of: find.byTooltip(tooltip), matching: find.byType(IconButton));

Finder _richText(String needle) =>
    find.textContaining(needle, findRichText: true);

/// The three split children must sum to the available height. Inserting the bar
/// at full height while the panes still animated from their old heights used to
/// overflow the column by exactly the bar height for a frame.
void _expectNoOverflow(WidgetTester tester) {
  expect(tester.takeException(), isNull);
}

/// The reader assumes a phone viewport; the 800x600 test default overflows.
Future<void> _pumpReader(
  WidgetTester tester,
  LibraryController library,
  AsrClient client,
) async {
  tester.view.physicalSize = const Size(411, 891);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(_readerHarness(library, client));
  // The split panes animate their heights; assert only on the settled layout.
  await tester.pump(const Duration(milliseconds: 400));
  _expectNoOverflow(tester);
}

/// Move a cursor and re-render. The model mutates before the first await, so
/// the returned future (cursor sync, prefs) does not need to complete here.
Future<void> _settle(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));
  _expectNoOverflow(tester);
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  testWidgets('reader renders the sentence at the current cursor',
      (tester) async {
    final client = _mockClient();
    final library = LibraryController(client: client)..session = _session();

    await _pumpReader(tester, library, client);

    expect(_richText('Sentence body number 0.'), findsWidgets);
  });

  testWidgets('advancing the sentence re-renders text but not the figure',
      (tester) async {
    final client = _mockClient();
    final library = LibraryController(client: client)..session = _session();

    await _pumpReader(tester, library, client);
    library.advanceSentence(1);
    await _settle(tester);

    expect(library.session!.sentenceIndex, 1);
    expect(library.session!.figureIndex, 0);
    expect(_richText('Sentence body number 1.'), findsWidgets);
    expect(_richText('Sentence body number 0.'), findsNothing);
  });

  testWidgets('advancing the figure leaves the rendered sentence untouched',
      (tester) async {
    final client = _mockClient();
    final library = LibraryController(client: client)
      ..session = _session()
      ..session!.sentenceIndex = 2;

    await _pumpReader(tester, library, client);
    library.advanceFigure(1);
    await _settle(tester);

    expect(library.session!.figureIndex, 1);
    expect(library.session!.sentenceIndex, 2);
    expect(_richText('Sentence body number 2.'), findsWidgets);
    expect(_richText('Sentence body number 1.'), findsNothing);
  });

  testWidgets('both nav chevron pairs are wired and enabled for a real paper',
      (tester) async {
    final client = _mockClient();
    final library = LibraryController(client: client)..session = _session();

    await _pumpReader(tester, library, client);

    for (final tip in <String>[
      'prev sentence',
      'next sentence',
      'prev figure',
      'next figure',
    ]) {
      expect(_chevron(tip), findsOneWidget, reason: '$tip chevron missing');
      expect(
        tester.widget<IconButton>(_chevron(tip)).onPressed,
        isNotNull,
        reason: '$tip chevron disabled',
      );
    }
  });

  testWidgets('sentence chevrons are disabled when the paper has no sentences',
      (tester) async {
    final client = _mockClient();
    final library = LibraryController(client: client)
      ..session = _session(sentences: 0, figures: 1);

    await _pumpReader(tester, library, client);

    expect(tester.widget<IconButton>(_chevron('next sentence')).onPressed, isNull);
    expect(tester.widget<IconButton>(_chevron('prev sentence')).onPressed, isNull);
  });

  // design/435 — [_pumpReader] stops on the first frame of the pane animation.
  // These tests play it out; a pane passing through a few pixels reports an
  // overflow on the way, which the ClipRect around it hides.
  Future<void> animate(WidgetTester tester) async {
    for (var i = 0; i < 10; i++) {
      await tester.pump(const Duration(milliseconds: 50));
      final e = tester.takeException();
      if (e != null &&
          !'$e'.contains('overflowed') &&
          !'$e'.contains('Multiple exceptions')) {
        fail('$e');
      }
    }
  }

  Future<void> tapSentence(WidgetTester tester) async {
    await tester.tap(_richText('Sentence body number 0.').first);
    await tester.pump(const Duration(milliseconds: 400));
    await animate(tester);
  }

  // design/435 — the tap that hides the sentence buttons also hides the title
  // row and a folded references row; another tap brings them back.
  testWidgets('a tap hides the title row and the folded references row',
      (tester) async {
    ReaderPrefs.instance.resetForTests();
    final client = _mockClient();
    final library = LibraryController(client: client)..session = _session();

    await _pumpReader(tester, library, client);
    await animate(tester);
    expect(find.text('Independent Cursor Paper'), findsOneWidget);
    expect(find.text('참고문헌'), findsOneWidget);

    await tester.tap(find.text('참고문헌'));
    await animate(tester);
    await tapSentence(tester);
    expect(find.text('Independent Cursor Paper'), findsNothing);
    expect(find.text('참고문헌'), findsNothing);
    expect(find.byTooltip('next sentence'), findsNothing);

    await tapSentence(tester);
    expect(find.text('Independent Cursor Paper'), findsOneWidget);
    expect(find.text('참고문헌'), findsOneWidget);
  });

  testWidgets('an open references row stays when a tap hides the buttons',
      (tester) async {
    ReaderPrefs.instance.resetForTests();
    final client = _mockClient();
    final library = LibraryController(client: client)..session = _session();

    await _pumpReader(tester, library, client);
    await animate(tester);
    await tapSentence(tester);
    expect(find.text('Independent Cursor Paper'), findsNothing);
    expect(find.text('참고문헌'), findsOneWidget);
  });

  testWidgets('the phone sentence uses the size from settings', (tester) async {
    ReaderPrefs.instance.resetForTests();
    await ReaderPrefs.instance.setSentencePx(32);
    final client = _mockClient();
    final library = LibraryController(client: client)..session = _session();

    await _pumpReader(tester, library, client);
    await animate(tester);
    final sizes = <double?>[];
    for (final rt in tester.widgetList<RichText>(
        _richText('Sentence body number 0.'))) {
      rt.text.visitChildren((span) {
        if (span is TextSpan && (span.text ?? '').contains('Sentence body')) {
          sizes.add(span.style?.fontSize);
        }
        return true;
      });
      sizes.add((rt.text as TextSpan).style?.fontSize);
    }
    expect(sizes, contains(32.0));
    ReaderPrefs.instance.resetForTests();
  });

  double sentenceCardHeight(WidgetTester tester) {
    final card = find.ancestor(
      of: _richText('Sentence body number 0.').first,
      matching: find.byType(Card),
    );
    return tester.getSize(card.first).height;
  }

  testWidgets('the split opens where the reader last left the bar',
      (tester) async {
    ReaderPrefs.instance.resetForTests();
    final client = _mockClient();
    final library = LibraryController(client: client)..session = _session();
    await _pumpReader(tester, library, client);
    await animate(tester);
    final atDefault = sentenceCardHeight(tester);

    await tester.pumpWidget(const SizedBox());
    await ReaderPrefs.instance.setSplitFraction(0.35);
    final library2 = LibraryController(client: client)..session = _session();
    await _pumpReader(tester, library2, client);
    await animate(tester);
    final atSaved = sentenceCardHeight(tester);
    expect(atSaved, lessThan(atDefault - 100));
    ReaderPrefs.instance.resetForTests();
  });

  testWidgets('dragging the bar saves where it was left', (tester) async {
    ReaderPrefs.instance.resetForTests();
    final client = _mockClient();
    final library = LibraryController(client: client)..session = _session();
    await _pumpReader(tester, library, client);
    await animate(tester);

    final bar = find.byWidgetPredicate(
      (w) => w.runtimeType.toString() == '_SplitHandle',
    );
    expect(bar, findsOneWidget);
    await tester.drag(bar, const Offset(0, -220));
    await animate(tester);

    final saved = ReaderPrefs.instance.splitFraction;
    expect(saved, lessThan(0.5));
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getDouble(ReaderPrefs.splitKey), saved);
    ReaderPrefs.instance.resetForTests();
  });

  // design/436 — the phone sentence takes the font, line height, spacing and
  // line width from the reading settings.
  TextStyle? sentenceStyle(WidgetTester tester) {
    TextStyle? found;
    for (final rt in tester.widgetList<RichText>(
        _richText('Sentence body number 0.'))) {
      rt.text.visitChildren((span) {
        if (span is TextSpan &&
            (span.text ?? '').contains('Sentence body') &&
            span.style?.fontSize != null) {
          found ??= span.style;
        }
        return true;
      });
    }
    return found;
  }

  testWidgets('the phone sentence uses the chosen font, line height and spacing',
      (tester) async {
    ReaderPrefs.instance.resetForTests();
    final web = WebReadingPrefs.instance..resetForTests();
    await web.setFont(WebFont.literata);
    await web.setLineGap(WebLineGap.wider);
    await web.setSpacing(WebSpacing.wide);
    final client = _mockClient();
    final library = LibraryController(client: client)..session = _session();

    await _pumpReader(tester, library, client);
    await animate(tester);
    final style = sentenceStyle(tester)!;
    expect(style.fontFamily, 'Literata');
    expect(style.height, 2.2);
    expect(style.letterSpacing, closeTo(16 * 0.05, 1e-9));
    web.resetForTests();
  });

  testWidgets('a narrow line width moves the phone sentence in from the sides',
      (tester) async {
    ReaderPrefs.instance.resetForTests();
    final web = WebReadingPrefs.instance..resetForTests();
    final client = _mockClient();
    final library = LibraryController(client: client)..session = _session();
    await _pumpReader(tester, library, client);
    await animate(tester);
    final medium = tester.getTopLeft(_richText('Sentence body number 0.').first).dx;

    await web.setColumn(WebColumnWidth.narrow);
    await animate(tester);
    final narrow = tester.getTopLeft(_richText('Sentence body number 0.').first).dx;
    expect(narrow - medium,
        closeTo(kPhoneColumnInset[WebColumnWidth.narrow]! -
            kPhoneColumnInset[WebColumnWidth.medium]!, 0.5));
    web.resetForTests();
  });

  test('design/436 the phone page colour loads and saves, and starts at the app theme',
      () async {
    SharedPreferences.setMockInitialValues({ReaderPrefs.pageKey: 'paper'});
    final prefs = ReaderPrefs.instance..resetForTests();
    expect(prefs.page, WebPage.app);
    await prefs.load();
    expect(prefs.page, WebPage.paper);
    await prefs.setPage(WebPage.dim);
    final p = await SharedPreferences.getInstance();
    expect(p.getString(ReaderPrefs.pageKey), 'dim');
    prefs.resetForTests();
  });

  // design/437 — the phone sentence sits a little above the middle of its pane.
  testWidgets('a short phone sentence sits a little above the middle of its pane',
      (tester) async {
    ReaderPrefs.instance.resetForTests();
    WebReadingPrefs.instance.resetForTests();
    final client = _mockClient();
    final library = LibraryController(client: client)..session = _session();
    await _pumpReader(tester, library, client);
    await animate(tester);

    final text = tester.getRect(_richText('Sentence body number 0.').first);
    final card = tester.getRect(find
        .ancestor(
          of: _richText('Sentence body number 0.').first,
          matching: find.byType(Card),
        )
        .first);
    final at = (text.center.dy - card.top) / card.height;
    expect(at, greaterThan(0.3));
    expect(at, lessThan(0.5));
  });

  testWidgets('the phone names a new section above its first sentence',
      (tester) async {
    ReaderPrefs.instance.resetForTests();
    WebReadingPrefs.instance.resetForTests();
    final client = _mockClient();
    final library = LibraryController(client: client)..session = _session();
    await _pumpReader(tester, library, client);
    await animate(tester);
    final name = sectionStartLabel(library.session!.sentences, 0);
    expect(name, isNotEmpty);

    await tapSentence(tester);
    expect(find.byTooltip('next sentence'), findsNothing);
    expect(find.text(name), findsOneWidget);

    library.advanceSentence(1);
    await animate(tester);
    expect(find.text(name), findsNothing);
  });

  // design/441 — the references fold is the reader's, for every paper.
  Finder citeIcon(IconData icon) => find.descendant(
        of: find.ancestor(of: find.text('참고문헌'), matching: find.byType(Row)).first,
        matching: find.byIcon(icon),
      );

  testWidgets('folded references stay folded in the next paper', (tester) async {
    ReaderPrefs.instance.resetForTests();
    final client = _mockClient();
    final first = LibraryController(client: client)..session = _session();
    await _pumpReader(tester, first, client);
    await animate(tester);
    expect(citeIcon(Icons.expand_less), findsOneWidget);

    await tester.tap(find.text('참고문헌'));
    await animate(tester);
    expect(citeIcon(Icons.expand_more), findsOneWidget);
    final p = await SharedPreferences.getInstance();
    expect(p.getBool(ReaderPrefs.citeCollapsedKey), isTrue);

    await tester.pumpWidget(const SizedBox());
    final second = LibraryController(client: client)
      ..session = _session(cacheId: 'c2');
    await _pumpReader(tester, second, client);
    await animate(tester);
    expect(citeIcon(Icons.expand_more), findsOneWidget);

    await tester.tap(find.text('참고문헌'));
    await animate(tester);
    expect(citeIcon(Icons.expand_less), findsOneWidget);
    expect(p.getBool(ReaderPrefs.citeCollapsedKey), isFalse);
    ReaderPrefs.instance.resetForTests();
  });

  test('design/441 the references fold loads from the saved value', () async {
    SharedPreferences.setMockInitialValues({ReaderPrefs.citeCollapsedKey: true});
    final prefs = ReaderPrefs.instance..resetForTests();
    expect(prefs.citeCollapsed, isFalse);
    await prefs.load();
    expect(prefs.citeCollapsed, isTrue);
    prefs.resetForTests();
  });

  // design/442 — next on the last sentence asks, as an e-book's last page does.
  testWidgets('next on the last sentence asks to mark the paper read',
      (tester) async {
    ReaderPrefs.instance.resetForTests();
    final client = _mockClient();
    final library = LibraryController(client: client)
      ..session = _session()
      ..session!.sentenceIndex = 2;
    await _pumpReader(tester, library, client);

    library.advanceSentence(1);
    await _settle(tester);
    expect(find.text('다 읽은 논문으로 표시할까요?'), findsOneWidget);

    await tester.tap(find.text('아니요'));
    await _settle(tester);
    expect(library.session!.sentenceIndex, 2);
    expect(library.readDone.isDone('c1'), isFalse);

    library.advanceSentence(1);
    await _settle(tester);
    await tester.tap(find.text('예'));
    await _settle(tester);
    expect(library.readDone.isDone('c1'), isTrue);
    expect(library.session!.sentenceIndex, 2);
    expect(find.text('다 읽은 논문으로 표시했어요.'), findsOneWidget);

    await tester.pump(const Duration(seconds: 3));
    await _settle(tester);
    library.advanceSentence(1);
    await _settle(tester);
    expect(find.text('다 읽은 논문으로 표시할까요?'), findsNothing);
    expect(find.text('마지막 문장이에요. 다 읽은 논문이에요.'), findsOneWidget);
    expect(library.session!.sentenceIndex, 2);
    await tester.pump(const Duration(seconds: 3));
    await _settle(tester);
  });

  testWidgets('without an open reader the last sentence still wraps',
      (tester) async {
    final client = _mockClient();
    final library = LibraryController(client: client)
      ..session = _session()
      ..session!.sentenceIndex = 2;
    await library.advanceSentence(1);
    expect(library.session!.sentenceIndex, 0);
  });
  // design/444 — the switch shows a long sentence in its pieces.
  testWidgets('a long sentence breaks into pieces when the switch is on',
      (tester) async {
    ReaderPrefs.instance.resetForTests();
    WebReadingPrefs.instance.resetForTests();
    const long = 'Our route uses a vapour growth method, which has several '
        'strengths, including (i) making even particles in a short process, '
        '(ii) giving easy control over mixtures, and (iii) being simple to '
        'scale up to large batches.';
    final client = _mockClient();
    final library = LibraryController(client: client)
      ..session = ReadingSession.fromOpenJson({
        'session_id': 'ses_long',
        'cache_id': 'c1',
        'title': 'Long Sentence Paper',
        'sentences': [
          {'id': 's0', 'text': long, 'section': 'results'},
        ],
        'figures': const [],
        'sentence_index': 0,
        'figure_index': 0,
      });
    await _pumpReader(tester, library, client);
    expect(_richText('method,\nwhich has'), findsNothing);

    await WebReadingPrefs.instance.setClauseBreaks(true);
    await _settle(tester);
    expect(_richText('method,\nwhich has'), findsOneWidget);
    expect(_richText('mixtures, and\n(iii) being'), findsOneWidget);
    WebReadingPrefs.instance.resetForTests();
  });
}
