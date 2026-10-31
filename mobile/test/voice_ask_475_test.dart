import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/voice_ask_models.dart';
import 'package:sentence_reading/services/shadow_mic.dart';
import 'package:sentence_reading/widgets/annotation_toolbar_sheet.dart';
import 'package:sentence_reading/widgets/voice_ask_overlay.dart';

class _FakeMic implements ShadowMic {
  _FakeMic({this.allowed = true, this.bytes = const [1, 2, 3]});

  final bool allowed;
  final List<int> bytes;
  final List<String> calls = [];
  double loud = 0.6;

  @override
  Future<bool> ensurePermission() async {
    calls.add('permission');
    return allowed;
  }

  @override
  Future<bool> prepare(String tag) async => true;

  @override
  Future<bool> start(String tag, {bool usePrimed = true}) async {
    calls.add('start:$tag');
    return true;
  }

  @override
  Future<MicTake?> stop() async {
    calls.add('stop');
    return MicTake(bytes: Uint8List.fromList(bytes), mime: 'audio/webm');
  }

  @override
  Future<void> cancel() async => calls.add('cancel');

  @override
  Future<double> level() async => loud;

  @override
  void dispose() => calls.add('dispose');
}

Duration ms(int v) => Duration(milliseconds: v);

void main() {
  test('design/475 the take clock', () {
    expect(voiceAskClock(const Duration(seconds: 7)), '0:07');
    expect(voiceAskClock(const Duration(seconds: 161)), '2:41');
  });

  test('design/475 the glow rises fast and settles slowly', () {
    final up = voiceGlowStep(0, 1);
    final down = 1 - voiceGlowStep(1, 0);
    expect(up, greaterThan(down * 3));
    expect(micLevelFromAmplitude(0), 0);
    expect(micLevelFromAmplitude(32767), 1);
    expect(micLevelFromAmplitude(3000), inExclusiveRange(0.2, 0.9));
    expect(micLevelFromRms(0), 0);
    expect(micLevelFromRms(0.05), inExclusiveRange(0.2, 0.9));
  });

  Widget field({
    required List<String> asked,
    _FakeMic? mic,
    VoiceAskTranscribe? transcribe,
    List<String>? sentences,
  }) {
    return MaterialApp(
      home: Scaffold(
        body: AiAskQuestionField(
          onAsk: asked.add,
          compact: false,
          voice: mic == null
              ? null
              : VoiceAskSource(
                  sentence: 'The catalyst works.',
                  newMic: () => mic,
                  transcribe: transcribe ??
                      (take, sentence) async {
                        sentences?.add(sentence);
                        return const VoiceAskHeard('이 catalyst 가 뭐야?');
                      },
                ),
        ),
      ),
    );
  }

  testWidgets('design/475 no voice source, no microphone', (tester) async {
    await tester.pumpWidget(field(asked: []));
    expect(find.byKey(const ValueKey('ai_ask_mic')), findsNothing);
    expect(find.byIcon(Icons.send), findsOneWidget);
  });

  testWidgets('design/475 speak, tap anywhere, the words land in the box with the hint',
      (tester) async {
    final asked = <String>[];
    final sentences = <String>[];
    final mic = _FakeMic();
    await tester.pumpWidget(field(asked: asked, mic: mic, sentences: sentences));
    await tester.tap(find.byKey(const ValueKey('ai_ask_mic')));
    await tester.pump();
    await tester.pump(ms(300));
    expect(find.textContaining(kVoiceAskListening), findsOneWidget);
    expect(find.textContaining(kVoiceAskTapToEnd), findsOneWidget);
    expect(mic.calls, ['permission', 'start:voice_ask']);

    await tester.pump(ms(1200));
    expect(find.text('0:01'), findsOneWidget);
    await tester.tapAt(const Offset(40, 300));
    await tester.pump();
    await tester.pump(ms(300));
    expect(find.textContaining(kVoiceAskListening), findsNothing);
    expect(mic.calls, containsAllInOrder(['stop', 'dispose']));
    expect(sentences, ['The catalyst works.']);
    expect(find.text('이 catalyst 가 뭐야?'), findsOneWidget);

    await tester.enterText(find.byType(TextField), '이 catalyst 가 뭐야? 쉽게');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pump();
    // design/498 — no "misheard" line in front of a spoken question.
    expect(asked, ['이 catalyst 가 뭐야? 쉽게']);

    await tester.enterText(find.byType(TextField), '');
    await tester.enterText(find.byType(TextField), '새로 쓴 질문');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pump();
    expect(asked.last, '새로 쓴 질문', reason: 'emptying the box drops the voice hint');
  });

  testWidgets('design/475 cancel and Esc leave the box alone', (tester) async {
    final asked = <String>[];
    final mic = _FakeMic();
    await tester.pumpWidget(field(asked: asked, mic: mic));
    await tester.tap(find.byKey(const ValueKey('ai_ask_mic')));
    await tester.pump();
    await tester.pump(ms(300));
    await tester.tap(find.byKey(const ValueKey('voice_ask_cancel')));
    await tester.pump();
    await tester.pump(ms(300));
    expect(find.textContaining(kVoiceAskListening), findsNothing);
    expect(mic.calls, isNot(contains('stop')));
    expect(tester.widget<TextField>(find.byType(TextField)).controller!.text, '');

    await tester.tap(find.byKey(const ValueKey('ai_ask_mic')));
    await tester.pump();
    await tester.pump(ms(300));
    expect(find.textContaining(kVoiceAskListening), findsOneWidget);
    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pump();
    await tester.pump(ms(300));
    expect(find.textContaining(kVoiceAskListening), findsNothing);
    expect(tester.widget<TextField>(find.byType(TextField)).controller!.text, '');
  });

  testWidgets('design/475 a refused microphone says how to allow it', (tester) async {
    final mic = _FakeMic(allowed: false);
    await tester.pumpWidget(field(asked: [], mic: mic));
    await tester.tap(find.byKey(const ValueKey('ai_ask_mic')));
    await tester.pump();
    await tester.pump(ms(300));
    expect(find.textContaining('허용한 뒤'), findsOneWidget);
    expect(find.byKey(const ValueKey('voice_ask_retry')), findsOneWidget);
    await tester.tapAt(const Offset(40, 300));
    await tester.pump();
    await tester.pump(ms(300));
    expect(find.textContaining('허용한 뒤'), findsNothing);
  });

  testWidgets('design/475 a failed write-down keeps the screen with a retry', (tester) async {
    final mic = _FakeMic();
    await tester.pumpWidget(field(
      asked: [],
      mic: mic,
      transcribe: (take, sentence) async => const VoiceAskHeard('', error: 'auth_required'),
    ));
    await tester.tap(find.byKey(const ValueKey('ai_ask_mic')));
    await tester.pump();
    await tester.pump(ms(300));
    await tester.tapAt(const Offset(40, 300));
    await tester.pump();
    await tester.pump(ms(300));
    expect(find.text(voiceAskErrorKo('auth_required')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('voice_ask_retry')));
    await tester.pump();
    await tester.pump(ms(300));
    expect(find.textContaining(kVoiceAskListening), findsOneWidget);
    expect(mic.calls.where((c) => c == 'start:voice_ask').length, 2);
    await tester.tap(find.byKey(const ValueKey('voice_ask_cancel')));
    await tester.pump();
    await tester.pump(ms(300));
  });

  test('design/475 the edge glow repaints as the voice changes', () {
    final a = VoiceEdgeGlowPainter(level: 0.2, turn: 0.1);
    expect(a.shouldRepaint(VoiceEdgeGlowPainter(level: 0.2, turn: 0.1)), isFalse);
    expect(a.shouldRepaint(VoiceEdgeGlowPainter(level: 0.5, turn: 0.1)), isTrue);
  });

  testWidgets('design/475 an empty recording is not sent to be written down', (tester) async {
    final sentences = <String>[];
    await tester.pumpWidget(field(asked: [], mic: _FakeMic(bytes: const []), sentences: sentences));
    await tester.tap(find.byKey(const ValueKey('ai_ask_mic')));
    await tester.pump();
    await tester.pump(ms(300));
    await tester.tapAt(const Offset(40, 300));
    await tester.pump();
    await tester.pump(ms(300));
    expect(find.textContaining('녹음된 소리가 없어요'), findsOneWidget);
    expect(sentences, isEmpty);
    await tester.tap(find.byKey(const ValueKey('voice_ask_cancel')));
    await tester.pump();
    await tester.pump(ms(300));
  });

  testWidgets('design/498 the microphone and send buttons are big', (tester) async {
    await tester.pumpWidget(field(asked: [], mic: _FakeMic()));
    final buttons = tester.widgetList<IconButton>(find.byType(IconButton)).toList();
    expect(buttons, hasLength(2));
    for (final b in buttons) {
      expect(b.iconSize, 34);
    }
  });

  test('design/498 a long press anywhere on the sentence card opens the sheet', () {
    final src = File('lib/screens/reader_screen.dart').readAsStringSync();
    expect(src, contains('onLongPress: widget.onLongPress,'));
    expect(src, isNot(contains(': GestureDetector(\n                            onLongPress: annotations.sentencePaintMode')));
  });
}
