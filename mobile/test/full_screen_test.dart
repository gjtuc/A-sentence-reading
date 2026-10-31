import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/services/full_screen.dart';

void main() {
  test('design/422: the phone has no full screen to ask for', () async {
    expect(fullScreenSupported, isFalse);
    expect(await enterFullScreen(), isFalse);
    expect(fullScreenOn.value, isFalse);
  });

  test('design/422: the main window waits for the figure window first', () {
    bool waits({
      bool main = true,
      bool autoPane = true,
      bool figureOpen = false,
      bool tried = false,
      bool gesturePending = false,
    }) =>
        fullScreenWaitsForPane(
          main: main,
          autoPane: autoPane,
          figureOpen: figureOpen,
          tried: tried,
          gesturePending: gesturePending,
        );

    expect(waits(), isTrue, reason: 'the figure window has not been tried yet');
    expect(waits(tried: true, gesturePending: true), isTrue,
        reason: 'this click opens the figure window');
    expect(waits(tried: true), isFalse);
    expect(waits(figureOpen: true), isFalse);
    expect(waits(autoPane: false), isFalse);
    expect(waits(main: false), isFalse, reason: 'the figure window itself never waits');
  });

  test('design/422: the Esc that left full screen is not a back', () {
    final t = DateTime(2026, 10, 19, 21);
    markFullScreenLeftForTests(t);
    expect(fullScreenJustLeft(now: t.add(const Duration(milliseconds: 100))), isTrue);
    expect(fullScreenJustLeft(now: t.add(const Duration(seconds: 1))), isFalse);
    markFullScreenLeftForTests(null);
    expect(fullScreenJustLeft(now: t), isFalse);
  });

  test('design/432: only the exit right after opening the AI window is a step away', () {
    final t = DateTime(2026, 10, 20, 20);
    expect(fullScreenSteppedAway(null, t), isFalse);
    expect(fullScreenSteppedAway(t, t.add(const Duration(milliseconds: 300))), isTrue);
    expect(fullScreenSteppedAway(t, t.add(const Duration(seconds: 5))), isFalse,
        reason: 'a later Esc is the user leaving, and the other window follows');
    expect(fullScreenSteppedAway(t, t.subtract(const Duration(seconds: 1))), isFalse);
  });

  test('design/502: an unused Esc leaves full screen and is not also a back', () async {
    expect(fullScreenTakesEscape(), isFalse, reason: 'out of full screen Esc goes back');
    fullScreenOn.value = true;
    expect(fullScreenTakesEscape(), isTrue);
    await Future<void>.delayed(Duration.zero);
    expect(fullScreenOn.value, isFalse);
    expect(fullScreenJustLeft(), isTrue);
  });
}
