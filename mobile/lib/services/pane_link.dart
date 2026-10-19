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

/// The figure window fills a screen other than [current] when there is one;
/// otherwise a window over this one.
String paneWindowFeatures(List<PaneScreen> screens, PaneScreen? current) {
  const plain = 'popup=yes,width=1100,height=850';
  if (current == null || screens.length < 2) return plain;
  for (final s in screens) {
    if (s.left == current.left && s.top == current.top) continue;
    return 'popup=yes,left=${s.left},top=${s.top},width=${s.width},height=${s.height}';
  }
  return plain;
}

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

  DateTime? _figureSeen;
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

  void _post(Map<String, Object?> m) {
    if (_closed) return;
    try {
      _channel.post({...m, 'id': windowId});
    } catch (_) {}
  }

  @visibleForTesting
  void handle(Map<String, Object?> m) {
    if (_closed || m['id'] == windowId) return;
    switch (m['t']) {
      case 'hello':
        if (role != PaneRole.main || m['role'] != PaneRole.figure.name) return;
        final was = figureOpen;
        _figureSeen = _now();
        if (!was) notifyListeners();
        if (!was || m['need'] == true) onSpotWanted?.call();
      case 'bye':
        if (role != PaneRole.main || m['role'] != PaneRole.figure.name) return;
        if (_figureSeen == null) return;
        _figureSeen = null;
        notifyListeners();
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
