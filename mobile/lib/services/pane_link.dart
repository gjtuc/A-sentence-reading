/// design/415 — two windows on two monitors: sentences in the main window, figures in
/// a second window opened from it (`?pane=figure`). Both live in the same browser, so
/// they talk over a BroadcastChannel without the server.
///
/// Messages are small JSON maps with the sender window id:
/// - `hello` every [kPaneBeat] with the role; a figure window with nothing open sets
///   `need`, and the main window answers with its spot.
/// - `spot` after every saved move: paper cache id, sentence and figure index.
/// - `bye` when a window closes.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';

import 'pane_window_stub.dart'
    if (dart.library.js_interop) 'pane_window_web.dart' as win;

const String kPaneChannelName = 'asr_pane_v1';
const Duration kPaneBeat = Duration(seconds: 2);

/// A figure window not heard from for this long counts as closed.
const Duration kPaneAlive = Duration(seconds: 5);

enum PaneRole { main, figure }

abstract class PaneChannel {
  void post(Map<String, Object?> message);
  set onMessage(void Function(Map<String, Object?> message)? handler);
  void close();
}

/// The role this window was opened with; null off the web.
PaneRole? paneRoleFromUrl(Uri url, {bool web = kIsWeb}) {
  if (!web) return null;
  return url.queryParameters['pane'] == 'figure' ? PaneRole.figure : PaneRole.main;
}

/// The address of the figure window for the app at [url].
Uri figurePaneUrl(Uri url) {
  final q = Map<String, String>.from(url.queryParameters)..['pane'] = 'figure';
  return url.replace(queryParameters: q, fragment: '');
}

PaneChannel? openPaneChannel() => win.openPaneChannel(kPaneChannelName);

bool openFigurePane() => win.openWindow(figurePaneUrl(Uri.base).toString(), 'asr_figure');

void onPaneWindowClose(void Function() handler) => win.onPageHide(handler);

/// design/423 — closes this window. Works for the figure window because the
/// main window opened it; a window typed in by hand stays.
void closeThisPaneWindow() => win.closeWindow();

/// design/420 — learn the screens so the figure window goes to another one.
/// [ask] shows the browser's 「window management」 question; it must run inside
/// a click. Without [ask] only an already given answer is used.
Future<bool> preparePaneScreens({bool ask = false}) => win.prepareScreens(ask: ask);

/// design/420 — a window opened without a click is a blocked popup unless the
/// site is allowed popups; the next click or key opens it instead. That click
/// also asks for the screens, so the next window goes to the other monitor.
void openFigurePaneOnNextGesture(bool Function() stillWanted) =>
    win.onNextGesture(() {
      if (!stillWanted()) return;
      openFigurePane();
      unawaited(preparePaneScreens(ask: true));
    });

typedef PaneScreen = ({int left, int top, int width, int height});

/// The screen for the figure window: one other than [current], if any.
PaneScreen? paneTargetScreen(List<PaneScreen> screens, PaneScreen? current) {
  if (current == null || screens.length < 2) return null;
  for (final s in screens) {
    if (s.left == current.left && s.top == current.top) continue;
    return s;
  }
  return null;
}

/// The figure window fills a screen other than [current] when there is one;
/// otherwise a window over this one.
String paneWindowFeatures(List<PaneScreen> screens, PaneScreen? current) {
  final s = paneTargetScreen(screens, current);
  if (s == null) return 'popup=yes,width=1100,height=850';
  return 'popup=yes,left=${s.left},top=${s.top},width=${s.width},height=${s.height}';
}

/// design/424 — the other screen, once the browser was allowed to tell.
PaneScreen? paneOtherScreen() => win.otherScreen();

/// design/424 — this window fills [s] like a maximized one. The web cannot
/// maximize; the outer size set here covers the same area.
void fillPaneScreen(PaneScreen s) => win.fillScreen(s);

/// design/424 — after a click, ask for the screens; [then] runs once allowed.
/// The question waits for the click to finish, so a figure window that the
/// same click opens comes first.
void askPaneScreensOnNextGesture(void Function() then) => win.onNextGesture(() {
      Timer.run(() {
        preparePaneScreens(ask: true).then((ok) {
          if (ok) then();
        });
      });
    });

/// Whether the main window should open the figure window on its own now.
bool paneAutoOpenDue({
  required bool enabled,
  required PaneRole? role,
  required bool figureOpen,
  required bool hasPaper,
  required bool tried,
}) =>
    enabled && role == PaneRole.main && hasPaper && !figureOpen && !tried;

class PaneLink extends ChangeNotifier {
  PaneLink({
    required PaneChannel channel,
    required this.role,
    required this.windowId,
    DateTime Function()? now,
  })  : _channel = channel,
        _now = now ?? DateTime.now {
    _channel.onMessage = handle;
  }

  final PaneChannel _channel;
  final PaneRole role;
  final String windowId;
  final DateTime Function() _now;

  /// A spot from the other window.
  void Function(String cacheId, int si, int fi)? onSpot;

  /// Main window: the figure window wants the current spot.
  void Function()? onSpotWanted;

  /// Figure window: true while it has no paper to show.
  bool Function()? needsSpot;

  /// design/423 — figure window: the last main window said bye.
  void Function()? onMainGone;

  /// design/424 — figure window: the main window says where to sit.
  void Function(PaneScreen screen)? onPlace;

  /// design/424 — main window: hello from a figure window that was not open.
  void Function()? onFigureCame;

  DateTime? _figureSeen;
  final Map<String, DateTime> _mainsSeen = {};
  bool _figureExpected = false;

  /// design/424 — main window: a figure window is on its way (opening on its
  /// own), so the figures already leave this window. Ends at its first hello.
  bool get figureExpected => _figureExpected;
  set figureExpected(bool next) {
    if (next == _figureExpected) return;
    _figureExpected = next;
    notifyListeners();
  }

  /// The main window shows sentences only.
  bool get figureShown => role == PaneRole.main && (figureOpen || _figureExpected);
  Timer? _beat;
  bool _closed = false;

  bool get figureOpen {
    final seen = _figureSeen;
    return role == PaneRole.main && seen != null && _now().difference(seen) < kPaneAlive;
  }

  void start() {
    _hello();
    _beat?.cancel();
    _beat = Timer.periodic(kPaneBeat, (_) => tick());
  }

  @visibleForTesting
  void tick() {
    _hello();
    if (_figureSeen != null && !figureOpen) {
      _figureSeen = null;
      notifyListeners();
    }
  }

  void _hello() => _post({
        't': 'hello',
        'role': role.name,
        if (role == PaneRole.figure && (needsSpot?.call() ?? false)) 'need': true,
      });

  void sendSpot(String cacheId, int si, int fi) {
    if (cacheId.trim().isEmpty) return;
    _post({'t': 'spot', 'cache': cacheId.trim(), 'si': si, 'fi': fi});
  }

  void leave() => _post({'t': 'bye', 'role': role.name});

  void sendPlace(PaneScreen s) => _post({
        't': 'place',
        'l': s.left,
        'tp': s.top,
        'w': s.width,
        'h': s.height,
      });

  void _post(Map<String, Object?> m) {
    if (_closed) return;
    try {
      _channel.post({...m, 'id': windowId});
    } catch (_) {}
  }

  @visibleForTesting
  void handle(Map<String, Object?> m) {
    if (_closed || m['id'] == windowId) return;
    final from = m['id'];
    if (role == PaneRole.figure && m['role'] == PaneRole.main.name && from is String) {
      if (m['t'] == 'hello') _mainsSeen[from] = _now();
      if (m['t'] == 'bye') {
        _mainsSeen.remove(from);
        final now = _now();
        _mainsSeen.removeWhere((_, seen) => now.difference(seen) >= kPaneAlive);
        if (_mainsSeen.isEmpty) onMainGone?.call();
        return;
      }
    }
    switch (m['t']) {
      case 'hello':
        if (role != PaneRole.main || m['role'] != PaneRole.figure.name) return;
        final was = figureOpen;
        _figureSeen = _now();
        if (!was) {
          _figureExpected = false;
          notifyListeners();
          onFigureCame?.call();
        }
        if (!was || m['need'] == true) onSpotWanted?.call();
      case 'bye':
        if (role != PaneRole.main || m['role'] != PaneRole.figure.name) return;
        if (_figureSeen == null) return;
        _figureSeen = null;
        notifyListeners();
      case 'place':
        if (role != PaneRole.figure) return;
        final l = m['l'], t = m['tp'], w = m['w'], h = m['h'];
        if (l is! int || t is! int || w is! int || h is! int || w < 200 || h < 200) return;
        onPlace?.call((left: l, top: t, width: w, height: h));
      case 'spot':
        final cache = m['cache'];
        final si = m['si'];
        final fi = m['fi'];
        if (cache is! String || si is! int || fi is! int) return;
        onSpot?.call(cache, si, fi);
    }
  }

  @override
  void dispose() {
    _beat?.cancel();
    leave();
    _closed = true;
    _channel.onMessage = null;
    _channel.close();
    super.dispose();
  }
}
