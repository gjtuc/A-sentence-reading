// design/480 - the sentence changes in place, starts at one height, and a
// still mark shows where.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:sentence_reading/state/web_reading_prefs.dart';
import 'package:sentence_reading/widgets/reader_wheel.dart';
import 'package:sentence_reading/widgets/sentence_anchor.dart';

Duration ms(int n) => Duration(milliseconds: n);

double _opacity(WidgetTester tester, Finder of) {
  final f = find.ancestor(of: of, matching: find.byType(Opacity));
  return f.evaluate().isEmpty ? 0 : tester.widget<Opacity>(f.first).opacity;
}

Widget _pane({required double head, required double body, double view = 600}) =>
    MediaQuery(
      data: const MediaQueryData(size: Size(400, 900)),
      child: Directionality(
      textDirection: TextDirection.ltr,
      child: Align(
        alignment: Alignment.topLeft,
        child: SizedBox(
          width: 400,
          child: SingleChildScrollView(
            child: SentenceAnchor(
              viewHeight: view,
              head: SizedBox(key: const Key('head'), height: head),
              body: SizedBox(key: const Key('body'), height: body),
            ),
          ),
        ),
      ),
    ));

void main() {
  test('the first line goes to its start, higher only to fit, never over the head', () {
    expect(sentenceTop(view: 600, head: 0, body: 50, start: 180), 180);
    expect(sentenceTop(view: 600, head: 0, body: 300, start: 180), 180);
    expect(sentenceTop(view: 600, head: 0, body: 500, start: 180), 100);
    expect(sentenceTop(view: 600, head: 0, body: 900, start: 180), 0);
    expect(sentenceTop(view: 600, head: 250, body: 50, start: 180), 250);
    expect(sentenceTop(view: 0, head: 40, body: 50, start: 180), 40);
  });

  testWidgets('short and longer sentences start at one height, the head right above',
      (tester) async {
    final tops = <double>[];
    for (final body in [40.0, 120.0, 300.0]) {
      await tester.pumpWidget(_pane(head: 0, body: body));
      tops.add(tester.getTopLeft(find.byKey(const Key('body'))).dy);
    }
    expect(tops, everyElement(closeTo(180, 0.01)), reason: 'a fifth of the 900 px window');

    await tester.pumpWidget(_pane(head: 0, body: 40, view: 300));
    expect(tester.getTopLeft(find.byKey(const Key('body'))).dy, closeTo(180, 0.01),
        reason: 'a shorter pane beside a figure keeps the start');

    await tester.pumpWidget(_pane(head: 90, body: 40));
    expect(tester.getTopLeft(find.byKey(const Key('body'))).dy, closeTo(180, 0.01));
    expect(tester.getTopLeft(find.byKey(const Key('head'))).dy, closeTo(90, 0.01));
    expect(tester.getSize(find.byType(SentenceAnchor)).height, 600);

    await tester.pumpWidget(_pane(head: 0, body: 900));
    expect(tester.getTopLeft(find.byKey(const Key('body'))).dy, 0);
    expect(tester.getSize(find.byType(SentenceAnchor)).height, 900);
  });

  test('the mark brightens once as a sentence arrives', () {
    expect(StartMark.alphaAt(0), StartMark.rest);
    expect(StartMark.alphaAt(0.1), StartMark.rest, reason: 'the old sentence is still dimming');
    expect(StartMark.alphaAt(0.21), closeTo(StartMark.peak, 1e-9));
    expect(StartMark.alphaAt(0.7), closeTo(StartMark.rest, 1e-9));
    expect(StartMark.peak, lessThanOrEqualTo(0.3));
  });

  testWidgets('the mark sits still left of the first line', (tester) async {
    const style = TextStyle(fontSize: 20, height: 1.6);
    const text = Text('A sentence.', style: style);
    expect(withStartMark(text, style: style, gutter: 2), same(text));

    await tester.pumpWidget(MaterialApp(
      home: Align(
        alignment: Alignment.topLeft,
        child: Padding(
          padding: const EdgeInsets.only(left: 12, top: 50),
          child: withStartMark(text, style: style, gutter: 12),
        ),
      ),
    ));
    final mark = find.byType(StartMark);
    final at = tester.getRect(mark);
    final line = tester.getRect(find.text('A sentence.'));
    expect(at.right, lessThan(line.left));
    expect(at.left, greaterThanOrEqualTo(0));
    expect(at.height, 20);
    expect(at.top, closeTo(line.top + (32 - 20) / 2, 0.01));

    Color ink() => (tester.widget<Container>(
          find.descendant(of: mark, matching: find.byType(Container)),
        ).decoration! as BoxDecoration)
            .color!;
    final rest = ink().a;
    await tester.pump(ms(210));
    expect(ink().a, greaterThan(rest));
    await tester.pumpAndSettle();
    expect(ink().a, 0);
    expect(tester.getRect(mark), at);
  });

  testWidgets('the sentence changes in place: no move, never two at once', (tester) async {
    Widget at(int key, int dir) => Directionality(
          textDirection: TextDirection.ltr,
          child: Align(
            alignment: Alignment.topLeft,
            child: SizedBox(
              width: 300,
              height: 300,
              child: SentenceFadeSwitcher(
                dir: dir,
                child: SizedBox(key: ValueKey(key), width: 300, height: 300),
              ),
            ),
          ),
        );
    await tester.pumpWidget(at(0, 0));
    await tester.pumpWidget(at(1, 1));
    await tester.pump(ms(16));
    var least = 2.0;
    for (var i = 0; i < 30; i++) {
      await tester.pump(ms(10));
      final old = _opacity(tester, find.byKey(const ValueKey(0)));
      final fresh = _opacity(tester, find.byKey(const ValueKey(1)));
      expect(old == 0 || fresh == 0, isTrue, reason: 'both drawn at one place would pile up');
      least = least < old + fresh ? least : old + fresh;
      for (final k in [0, 1]) {
        final f = find.byKey(ValueKey(k));
        if (f.evaluate().isNotEmpty) expect(tester.getTopLeft(f), Offset.zero);
      }
    }
    expect(least, greaterThanOrEqualTo(SentenceFadeSwitcher.floor - 0.01));
    expect(find.byType(Transform), findsNothing);
    await tester.pumpAndSettle();
    expect(_opacity(tester, find.byKey(const ValueKey(1))), 1);
  });

  test('long sentences break into pieces unless the reader turned it off', () async {
    SharedPreferences.setMockInitialValues({});
    final prefs = WebReadingPrefs.instance..resetForTests();
    await prefs.load();
    expect(prefs.clauseBreaks, isTrue);
    SharedPreferences.setMockInitialValues({WebReadingPrefs.clauseBreaksKey: false});
    prefs.resetForTests();
    await prefs.load();
    expect(prefs.clauseBreaks, isFalse);
    prefs.resetForTests();
  });

  test('design/482: the mark fades away over three seconds without a pause', () {
    expect(StartMark.life, const Duration(seconds: 3));
    var last = StartMark.alphaAt(0.7);
    for (var s = 0.75; s <= 3.0; s += 0.05) {
      final a = StartMark.alphaAt(s);
      expect(a, lessThan(last), reason: 'still fading at ${s.toStringAsFixed(2)} s');
      last = a;
    }
    expect(StartMark.alphaAt(1.85), closeTo(StartMark.rest / 2, 1e-3));
    expect(StartMark.alphaAt(3), 0);
    expect(StartMark.alphaAt(9), 0);
  });

  testWidgets('design/484: a start in pixels holds in a short and a tall pane',
      (tester) async {
    Future<double> top(double pane) async {
      await tester.pumpWidget(MediaQuery(
        data: const MediaQueryData(size: Size(400, 900)),
        child: Directionality(
          textDirection: TextDirection.ltr,
          child: Align(
            alignment: Alignment.topLeft,
            child: SizedBox(
              width: 400,
              child: SentenceAnchor(
                viewHeight: pane,
                startPx: 40,
                head: const SizedBox(height: 30),
                body: const SizedBox(key: Key('body'), height: 100),
              ),
            ),
          ),
        ),
      ));
      return tester.getTopLeft(find.byKey(const Key('body'))).dy;
    }

    expect(await top(300), 40);
    expect(await top(800), 40);
    expect(phoneSentenceStart(22), lessThan(900 * kSentenceStartAt / 3));
    expect(phoneSentenceStart(22), greaterThan(22 * 0.9 + 16));
  });

  test('design/502 the start mark is half as bright as before', () {
    expect(StartMark.rest, 0.08);
    expect(StartMark.peak, 0.15);
  });
}
