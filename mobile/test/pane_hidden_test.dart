// design/449 - a minimized or covered figure window does not take the figures.
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/services/pane_link.dart';

class _Hub {
  final List<_End> ends = [];

  _End join() {
    final e = _End(this);
    ends.add(e);
    return e;
  }
}

class _End implements PaneChannel {
  _End(this.hub);

  final _Hub hub;
  void Function(Map<String, Object?> message)? _handler;

  @override
  void post(Map<String, Object?> message) {
    for (final e in hub.ends) {
      if (!identical(e, this)) e._handler?.call(Map.of(message));
    }
  }

  @override
  set onMessage(void Function(Map<String, Object?> message)? handler) => _handler = handler;

  @override
  void close() {}
}

void main() {
  test('design/449 a hidden figure window leaves the figures in the main window', () {
    final now = DateTime(2026, 10, 25, 17);
    final hub = _Hub();
    final main = PaneLink(channel: hub.join(), role: PaneRole.main, windowId: 'm', now: () => now);
    var hidden = true;
    final fig = PaneLink(channel: hub.join(), role: PaneRole.figure, windowId: 'f', now: () => now)
      ..isHidden = () => hidden;

    fig.tick();
    expect(main.figureShown, isFalse);

    hidden = false;
    fig.sayHello();
    expect(main.figureShown, isTrue);

    hidden = true;
    fig.sayHello();
    expect(main.figureShown, isFalse, reason: 'minimized again, the figures come back');
  });

  test('design/449 a hidden figure window ends the wait for one', () {
    final now = DateTime(2026, 10, 25, 17);
    final hub = _Hub();
    final main = PaneLink(channel: hub.join(), role: PaneRole.main, windowId: 'm', now: () => now)
      ..figureExpected = true;
    final fig = PaneLink(channel: hub.join(), role: PaneRole.figure, windowId: 'f', now: () => now)
      ..isHidden = () => true;
    expect(main.figureShown, isTrue);
    fig.tick();
    expect(main.figureShown, isFalse);
  });

  test('design/449 a window with no hidden flag counts as shown', () {
    final now = DateTime(2026, 10, 25, 17);
    final hub = _Hub();
    final main = PaneLink(channel: hub.join(), role: PaneRole.main, windowId: 'm', now: () => now);
    final fig = PaneLink(channel: hub.join(), role: PaneRole.figure, windowId: 'f', now: () => now);
    fig.tick();
    expect(main.figureShown, isTrue);
  });
}
