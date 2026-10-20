import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/annotation_plain.dart';
import 'package:sentence_reading/api/ai_ask_prompt_models.dart';
import 'package:sentence_reading/api/ai_ask_prompt_store.dart';
import 'package:sentence_reading/widgets/annotation_toolbar_sheet.dart';

void main() {
  test('annotationPlainForSentence strips cite markers', () {
    const raw = 'Hello world.<sup>1</sup>';
    final plain = annotationPlainForSentence(raw);
    expect(plain.contains('1'), isFalse);
    expect(plain.contains('Hello'), isTrue);
  });

  test('clampCharRange normalizes and rejects empty', () {
    expect(clampCharRange(5, 2, 10), [2, 5]);
    expect(clampCharRange(3, 3, 10), isNull);
    expect(clampCharRange(-2, 100, 5), [0, 5]);
  });

  test('textQuoteSelectorForRange exact substring', () {
    const plain = 'The catalytic activity was measured.';
    final sel = textQuoteSelectorForRange(plain, 4, 13);
    expect(sel['exact'], 'catalytic');
    expect(sel['type'], 'TextQuoteSelector');
  });

  test('charRangeFromSelectorExact finds needle', () {
    const plain = 'The catalytic activity was measured.';
    final sel = textQuoteSelectorForRange(plain, 4, 13);
    expect(charRangeFromSelectorExact(plain, sel), [4, 13]);
  });

  test('buildAiAskClipboard uses two blank lines', () {
    final s = buildAiAskClipboard(
      sentencePlain: 'That ant is small.',
      promptBody: '이 문장에 포함된 단어와 문법을 설명해줘.',
    );
    expect(s, 'That ant is small.\n\n\n이 문장에 포함된 단어와 문법을 설명해줘.');
  });

  test('seed once then delete does not reseed', () async {
    final store = MemoryAiAskPromptStore();
    final first = await loadAiAskPromptsEnsuringSeed(store);
    expect(first, hasLength(1));
    expect(first.first.body, kAiAskSeedPromptBody);
    await store.save([]);
    final again = await loadAiAskPromptsEnsuringSeed(store);
    expect(again, isEmpty);
  });

  test('wordRangeAt snaps to full word', () {
    const plain = 'The catalytic activity was measured.';
    expect(wordRangeAt(plain, 4), [4, 13]); // catalytic
    expect(wordRangeAt(plain, 6), [4, 13]);
    expect(wordRangeAt(plain, 3), [0, 3]); // space → The
  });

  test('wordSnappedSelection expands by words', () {
    const plain = 'The catalytic activity was measured.';
    final range = wordSnappedSelection(
      plain: plain,
      anchorStart: 4,
      anchorEnd: 13,
      extentIndex: 20, // inside activity
    );
    expect(range, [4, 22]); // catalytic activity
  });

  test('design/419: the question rides in the AI Mode address on one line', () {
    final uri = aiAskModeUri(
      sentencePlain: 'That ant\nis small.',
      promptBody: '  이 문장의\n문법을 설명해줘. ',
    )!;
    expect(uri.host, 'www.google.com');
    expect(uri.path, '/search');
    expect(uri.queryParameters['udm'], '50');
    expect(uri.queryParameters['q'], '"That ant is small." 이 문장의 문법을 설명해줘.');
    expect(aiAskModeUri(sentencePlain: 'x', promptBody: '  '), isNull);
    expect(
      aiAskModeUri(sentencePlain: 'word ' * 3000, promptBody: 'explain'),
      isNull,
      reason: 'too long for an address: the clipboard path takes it',
    );
  });

  test('design/419: a letter or Enter opens the question box, shortcuts do not', () {
    KeyEvent down(LogicalKeyboardKey key, PhysicalKeyboardKey phys, String? ch) =>
        KeyDownEvent(
          physicalKey: phys,
          logicalKey: key,
          character: ch,
          timeStamp: Duration.zero,
        );
    bool opens(KeyEvent e, {bool ctrl = false}) =>
        aiAskOpensOnKey(e, ctrl: ctrl, alt: false, meta: false);
    final g = down(LogicalKeyboardKey.keyG, PhysicalKeyboardKey.keyG, 'g');
    expect(opens(g), isTrue);
    expect(opens(g, ctrl: true), isFalse);
    expect(opens(down(LogicalKeyboardKey.enter, PhysicalKeyboardKey.enter, '\r')), isTrue);
    expect(opens(down(LogicalKeyboardKey.space, PhysicalKeyboardKey.space, ' ')), isFalse);
    expect(
      opens(down(LogicalKeyboardKey.arrowLeft, PhysicalKeyboardKey.arrowLeft, null)),
      isFalse,
    );
    expect(
      opens(KeyUpEvent(
        physicalKey: PhysicalKeyboardKey.keyG,
        logicalKey: LogicalKeyboardKey.keyG,
        timeStamp: Duration.zero,
      )),
      isFalse,
    );
  });

  test('design/433 neighbour sentence keeps its scripts, not its cites', () {
    const raw = 'Loading was 0.25 mg<sub>Pt</sub> cm<sup>\u22122</sup>.<sup>12</sup>';
    const style = TextStyle(fontSize: 20);
    final spans = annotationRichSpansForSentence(raw, style);
    expect(spans.whereType<WidgetSpan>().length, 2);
    expect(spans.map((s) => s.toPlainText()).join().contains('12'), isFalse);
  });
}
