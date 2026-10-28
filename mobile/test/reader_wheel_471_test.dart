import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/ai_ask_prompt_store.dart';
import 'package:sentence_reading/widgets/annotation_toolbar_sheet.dart';
import 'package:sentence_reading/widgets/reader_wheel.dart';

Duration ms(int v) => Duration(milliseconds: v);

int turn(WheelStepper s, int t, double dy) {
  s.seen(ms(t));
  return s.won(ms(t), dy);
}

Future<void> wheel(WidgetTester tester, Offset at, double dy, int t) async {
  final p = TestPointer(1, PointerDeviceKind.mouse);
  await tester.sendEventToBinding(p.hover(at, timeStamp: ms(t)));
  await tester.sendEventToBinding(p.scroll(Offset(0, dy), timeStamp: ms(t)));
  await tester.pump();
}

class _Counted extends StatefulWidget {
  const _Counted({super.key, required this.inits});
  final List<int> inits;
  @override
  State<_Counted> createState() => _CountedState();
}

class _CountedState extends State<_Counted> {
  @override
  void initState() {
    super.initState();
    widget.inits.add(1);
  }

  @override
  Widget build(BuildContext context) =>
      const SizedBox(width: 200, height: 200, child: Text('s'));
}

void main() {
  test('design/471 a wheel notch steps once, down is next and up is previous', () {
    final s = WheelStepper();
    expect(turn(s, 0, 100), 1);
    expect(turn(s, 600, -100), -1);
  });

  test('design/471 a touchpad swipe of small events steps only once', () {
    final s = WheelStepper();
    var steps = 0;
    for (var t = 0; t <= 300; t += 16) {
      steps += turn(s, t, 6).abs();
    }
    expect(steps, 1);
  });

  test('design/471 a turn used by an inner scroller does not step; the next turn does', () {
    final s = WheelStepper();
    s.seen(ms(0));
    s.seen(ms(16));
    expect(s.won(ms(16), 100), 0);
    expect(turn(s, 32, 100), 0);
    expect(turn(s, 400, 100), 1);
  });

  testWidgets('design/471 WheelPager steps on a plain wheel, not with Ctrl', (tester) async {
    final steps = <int>[];
    await tester.pumpWidget(Directionality(
      textDirection: TextDirection.ltr,
      child: WheelPager(
        onStep: steps.add,
        child: const ColoredBox(color: Color(0xFF000000), child: SizedBox.expand()),
      ),
    ));
    final c = tester.getCenter(find.byType(WheelPager));
    await wheel(tester, c, 100, 0);
    await wheel(tester, c, -100, 600);
    expect(steps, [1, -1]);
    await tester.sendKeyDownEvent(LogicalKeyboardKey.controlLeft);
    await wheel(tester, c, 100, 1200);
    await tester.sendKeyUpEvent(LogicalKeyboardKey.controlLeft);
    expect(steps, [1, -1]);
  });

  testWidgets('design/471 a long sentence scrolls to its end before the wheel turns it', (tester) async {
    final steps = <int>[];
    final ctrl = ScrollController();
    await tester.pumpWidget(Directionality(
      textDirection: TextDirection.ltr,
      child: WheelPager(
        onStep: steps.add,
        child: SingleChildScrollView(
          controller: ctrl,
          child: const SizedBox(height: 900, width: 100),
        ),
      ),
    ));
    final c = tester.getCenter(find.byType(WheelPager));
    var t = 0;
    for (var i = 0; i < 20; i++) {
      await wheel(tester, c, 100, t += 50);
    }
    expect(ctrl.offset, ctrl.position.maxScrollExtent);
    expect(steps, isEmpty);
    await wheel(tester, c, 100, t += 400);
    expect(steps, [1]);
  });

  testWidgets('design/471 the next sentence slides up from below', (tester) async {
    Widget at(int key, int dir) => Directionality(
          textDirection: TextDirection.ltr,
          child: Align(
            alignment: Alignment.topLeft,
            child: SizedBox(
              width: 200,
              height: 200,
              child: SentenceSlideSwitcher(
                dir: dir,
                child: SizedBox(key: ValueKey(key), width: 200, height: 200),
              ),
            ),
          ),
        );
    await tester.pumpWidget(at(0, 0));
    await tester.pumpWidget(at(1, 1));
    await tester.pump(ms(16));
    await tester.pump(ms(60));
    expect(tester.getTopLeft(find.byKey(const ValueKey(1))).dy, greaterThan(0));
    expect(tester.getTopLeft(find.byKey(const ValueKey(0))).dy, lessThan(0));
    await tester.pumpAndSettle();
    expect(tester.getTopLeft(find.byKey(const ValueKey(1))).dy, 0);
    expect(find.byKey(const ValueKey(0)), findsNothing);

    await tester.pumpWidget(at(2, 0));
    await tester.pump();
    expect(tester.getTopLeft(find.byKey(const ValueKey(2))).dy, 0);
  });

  testWidgets('design/471 the slide hint ending does not remount the sentence', (tester) async {
    final inits = <int>[];
    Widget at(int dir) => Directionality(
          textDirection: TextDirection.ltr,
          child: SentenceSlideSwitcher(
            dir: dir,
            child: _Counted(key: const ValueKey(5), inits: inits),
          ),
        );
    await tester.pumpWidget(at(1));
    await tester.pumpWidget(at(0));
    await tester.pumpWidget(at(-1));
    expect(inits.length, 1);
  });

  testWidgets('design/471 the question box is several lines tall and Enter sends it', (tester) async {
    final asked = <String>[];
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Column(children: [
          AiAskQuestionField(onAsk: asked.add),
          const TextField(key: ValueKey('one')),
        ]),
      ),
    ));
    final field = tester.widget<TextField>(
      find.descendant(of: find.byType(AiAskQuestionField), matching: find.byType(TextField)),
    );
    expect(field.minLines, 3);
    expect(field.maxLines, 5);
    expect(field.keyboardType, TextInputType.text);
    final h = tester.getSize(find.byType(AiAskQuestionField)).height;
    expect(h, greaterThan(tester.getSize(find.byKey(const ValueKey('one'))).height * 1.6));

    await tester.enterText(find.byType(AiAskQuestionField), '이 문장 쉽게 설명해 줘');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pump();
    expect(asked, ['이 문장 쉽게 설명해 줘']);
  });

  testWidgets('design/471 the sheet opens with AI ask on top and the sentence above the box', (tester) async {
    await tester.binding.setSurfaceSize(const Size(400, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(MaterialApp(
      home: Builder(
        builder: (context) => TextButton(
          onPressed: () => showAnnotationToolbarSheet(
            context: context,
            promptStore: MemoryAiAskPromptStore(),
            sentencePlain: 'The cat sat on the mat.',
          ),
          child: const Text('open'),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    final ai = tester.getTopLeft(find.text('AI로 묻기')).dy;
    final sentence = tester.getTopLeft(find.text('The cat sat on the mat.')).dy;
    final box = tester.getTopLeft(find.byType(AiAskQuestionField)).dy;
    final paint = tester.getTopLeft(find.text('하이라이트')).dy;
    expect(ai < sentence && sentence < box && box < paint, isTrue);
  });
  testWidgets('design/472 the slide plays even when the system asks for less motion', (tester) async {
    Widget at(int key, int dir) => MediaQuery(
          data: const MediaQueryData(disableAnimations: true),
          child: Directionality(
            textDirection: TextDirection.ltr,
            child: Align(
              alignment: Alignment.topLeft,
              child: SizedBox(
                width: 200,
                height: 200,
                child: SentenceSlideSwitcher(
                  dir: dir,
                  child: SizedBox(key: ValueKey(key), width: 200, height: 200),
                ),
              ),
            ),
          ),
        );
    await tester.pumpWidget(at(0, 0));
    await tester.pumpWidget(at(1, 1));
    await tester.pump(ms(60));
    expect(tester.getTopLeft(find.byKey(const ValueKey(1))).dy, greaterThan(0));
    await tester.pumpAndSettle();
  });

  testWidgets('design/472 the web question box stays thin and wraps to two lines', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(body: AiAskQuestionField(onAsk: (_) {}, compact: true)),
    ));
    final field = tester.widget<TextField>(find.byType(TextField));
    expect(field.minLines, 1);
    expect(field.maxLines, 2);
    expect(field.decoration?.isDense, isTrue);
  });
  testWidgets('design/474 the slide starts after the first frame of the new sentence', (tester) async {
    Widget at(int key, int dir) => Directionality(
          textDirection: TextDirection.ltr,
          child: Align(
            alignment: Alignment.topLeft,
            child: SizedBox(
              width: 200,
              height: 200,
              child: SentenceSlideSwitcher(
                dir: dir,
                child: SizedBox(key: ValueKey(key), width: 200, height: 200),
              ),
            ),
          ),
        );
    await tester.pumpWidget(at(0, 0));
    await tester.pumpWidget(at(1, 1));
    expect(tester.getTopLeft(find.byKey(const ValueKey(1))).dy, 200 * SentenceSlideSwitcher.travel);
    expect(tester.getTopLeft(find.byKey(const ValueKey(0))).dy, 0);
    await tester.pump(ms(16));
    await tester.pump(ms(100));
    final mid = tester.getTopLeft(find.byKey(const ValueKey(1))).dy;
    expect(mid, greaterThan(0));
    expect(mid, lessThan(200 * SentenceSlideSwitcher.travel));
    await tester.pumpWidget(at(0, -1));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey(1)), findsNothing);
    expect(tester.getTopLeft(find.byKey(const ValueKey(0))).dy, 0);
  });
}
