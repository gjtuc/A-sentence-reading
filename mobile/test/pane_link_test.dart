// design/415 - the main window and the figure window over one channel.
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

/// Like a BroadcastChannel: a post reaches every other end, never the sender.
class _End implements PaneChannel {
  _End(this.hub);

  final _Hub hub;
  void Function(Map<String, Object?> message)? _handler;
  bool closed = false;

  @override
  void post(Map<String, Object?> message) {
    for (final e in hub.ends) {
      if (!identical(e, this) && !e.closed) e._handler?.call(Map.of(message));
    }
  }

  @override
  set onMessage(void Function(Map<String, Object?> message)? handler) => _handler = handler;

  @override
  void close() => closed = true;
}

void main() {
  test('the role comes from the address, and only on the web', () {
    final app = Uri.parse('https://x.run.app/app/');
    expect(paneRoleFromUrl(app, web: false), isNull);
    expect(paneRoleFromUrl(app, web: true), PaneRole.main);
    final fig = figurePaneUrl(Uri.parse('https://x.run.app/app/?a=1#/reader'));
    expect(fig.queryParameters, {'a': '1', 'pane': 'figure'});
    expect(fig.fragment, isEmpty);
    expect(paneRoleFromUrl(fig, web: true), PaneRole.figure);
  });

  test('a figure window counts as open while it says hello', () {
    var now = DateTime(2026, 10, 19, 2);
    final hub = _Hub();
    final main = PaneLink(channel: hub.join(), role: PaneRole.main, windowId: 'm', now: () => now);
    final fig = PaneLink(channel: hub.join(), role: PaneRole.figure, windowId: 'f', now: () => now);
    var wanted = 0;
    var changes = 0;
    main.onSpotWanted = () => wanted++;
    main.addListener(() => changes++);
    expect(main.figureOpen, isFalse);
    fig.tick();
    expect(main.figureOpen, isTrue);
    expect(wanted, 1);
    expect(changes, 1);
    now = now.add(const Duration(seconds: 2));
    fig.tick();
    expect(wanted, 1);
    expect(changes, 1);
    now = now.add(kPaneAlive);
    main.tick();
    expect(main.figureOpen, isFalse);
    expect(changes, 2);
    fig.tick();
    fig.leave();
    expect(main.figureOpen, isFalse);
    expect(changes, 4);
    expect(fig.figureOpen, isFalse);
  });

  test('a figure window with nothing open asks for the spot on every hello', () {
    final hub = _Hub();
    final main = PaneLink(channel: hub.join(), role: PaneRole.main, windowId: 'm');
    final fig = PaneLink(channel: hub.join(), role: PaneRole.figure, windowId: 'f');
    var wanted = 0;
    var empty = true;
    main.onSpotWanted = () => wanted++;
    fig.needsSpot = () => empty;
    fig.tick();
    fig.tick();
    expect(wanted, 2);
    empty = false;
    fig.tick();
    expect(wanted, 2);
  });

  test('spots cross both ways and a window never hears itself', () {
    final hub = _Hub();
    final main = PaneLink(channel: hub.join(), role: PaneRole.main, windowId: 'm');
    final fig = PaneLink(channel: hub.join(), role: PaneRole.figure, windowId: 'f');
    final atMain = <String>[];
    final atFig = <String>[];
    main.onSpot = (c, si, fi) => atMain.add('$c:$si:$fi');
    fig.onSpot = (c, si, fi) => atFig.add('$c:$si:$fi');
    main.sendSpot('abc', 5, 2);
    fig.sendSpot('abc', 5, 3);
    main.sendSpot('  ', 1, 1);
    expect(atFig, ['abc:5:2']);
    expect(atMain, ['abc:5:3']);
    main.handle({'t': 'spot', 'id': 'm', 'cache': 'abc', 'si': 9, 'fi': 9});
    main.handle({'t': 'spot', 'id': 'x', 'cache': 'abc', 'si': '9', 'fi': 9});
    expect(atMain, ['abc:5:3']);
  });

  test('a disposed link says bye and goes quiet', () {
    final hub = _Hub();
    final main = PaneLink(channel: hub.join(), role: PaneRole.main, windowId: 'm');
    final figEnd = hub.join();
    final fig = PaneLink(channel: figEnd, role: PaneRole.figure, windowId: 'f');
    fig.tick();
    expect(main.figureOpen, isTrue);
    fig.dispose();
    expect(main.figureOpen, isFalse);
    expect(figEnd.closed, isTrue);
    main.dispose();
  });

  test('design/420: the figure window fills the other monitor when there is one', () {
    const left = (left: 0, top: 0, width: 1920, height: 1040);
    const right = (left: 1920, top: 0, width: 2560, height: 1400);
    expect(
      paneWindowFeatures(const [left, right], left),
      'popup=yes,left=1920,top=0,width=2560,height=1400',
    );
    expect(
      paneWindowFeatures(const [left, right], right),
      'popup=yes,left=0,top=0,width=1920,height=1040',
    );
    expect(paneWindowFeatures(const [left], left), 'popup=yes,width=1100,height=850');
    expect(paneWindowFeatures(const [], null), 'popup=yes,width=1100,height=850');
  });

  test('design/420: the main window opens it once, with a paper, when asked', () {
    bool due({
      bool enabled = true,
      PaneRole? role = PaneRole.main,
      bool figureOpen = false,
      bool hasPaper = true,
      bool tried = false,
    }) =>
        paneAutoOpenDue(
          enabled: enabled,
          role: role,
          figureOpen: figureOpen,
          hasPaper: hasPaper,
          tried: tried,
        );
    expect(due(), isTrue);
    expect(due(enabled: false), isFalse);
    expect(due(role: PaneRole.figure), isFalse);
    expect(due(role: null), isFalse);
    expect(due(figureOpen: true), isFalse);
    expect(due(hasPaper: false), isFalse);
    expect(due(tried: true), isFalse, reason: 'a closed figure window stays closed');
  });

  test('design/423: the figure window closes with the last main window', () {
    var now = DateTime(2026, 10, 19, 21);
    final hub = _Hub();
    final main = PaneLink(channel: hub.join(), role: PaneRole.main, windowId: 'm', now: () => now);
    final other = PaneLink(channel: hub.join(), role: PaneRole.main, windowId: 'o', now: () => now);
    final fig = PaneLink(channel: hub.join(), role: PaneRole.figure, windowId: 'f', now: () => now);
    var gone = 0;
    fig.onMainGone = () => gone++;
    main.tick();
    other.tick();

    other.leave();
    expect(gone, 0, reason: 'another main window is still there');
    now = now.add(kPaneAlive);
    main.tick();
    main.leave();
    expect(gone, 1);

    main.leave();
    expect(gone, 2, reason: 'a bye from a main never heard still means it closed');
    fig.leave();
    expect(gone, 2, reason: 'its own bye and a figure bye do not count');
    main.dispose();
    other.dispose();
    fig.dispose();
  });
}
