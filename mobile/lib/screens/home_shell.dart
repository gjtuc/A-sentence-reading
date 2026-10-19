import 'dart:async';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';

import '../api/access_models.dart';
import '../api/access_sticky_store.dart';
import '../state/auth_controller.dart';
import '../state/library_controller.dart';
import '../state/cite_panel_controller.dart';
import '../state/bookmark_controller.dart';
import '../state/annotation_controller.dart';
import '../state/shadowing_controller.dart';
import '../state/theme_controller.dart';
import '../state/translate_controller.dart';
import '../state/tts_controller.dart';
import '../state/web_reading_prefs.dart';
import '../api/launch_dest.dart';
import '../api/practice_cloud_sync.dart';
import '../services/evidence_bus.dart';
import '../services/full_screen.dart';
import '../services/pane_link.dart';
import 'access_waiting_screen.dart';
import 'library_screen.dart';
import 'login_screen.dart';
import 'reader_screen.dart';
import 'settings_screen.dart';
import 'shadowing_practice_screen.dart';

/// Auth-gated shell (design/68) + access waiting (design/84) + sticky (172).
///
/// Logged out → login only.
/// Logged in · invite pending/denied → waiting only.
/// Allowed / gate off → library home + reader surface + settings push (design/224).
class HomeShell extends StatefulWidget {
  const HomeShell({
    super.key,
    required this.auth,
    required this.library,
    required this.tts,
    required this.theme,
    required this.shadowing,
    required this.translate,
    required this.citePanel,
    required this.bookmarks,
    required this.annotations,
    this.accessSticky,
  });

  final AuthController auth;
  final LibraryController library;
  final TtsController tts;
  final ThemeController theme;
  final ShadowingController shadowing;
  final TranslateController translate;
  final CitePanelController citePanel;
  final BookmarkController bookmarks;
  final AnnotationController annotations;
  final AccessStickyStore? accessSticky;

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> with WidgetsBindingObserver {
  /// design/224 — library is home; reader is an overlay surface (no bottom tabs).
  bool _readerSurface = false;
  bool _readerMounted = false;
  /// null = not checked yet; true = may enter main tabs.
  bool? _accessUnlocked;
  /// design/172 — status timeout with no sticky → reconnect, not waiting shell.
  bool _accessRestorePending = false;
  Timer? _accessRetry;
  /// Last uid while logged-in — logout clears that sticky key.
  String _stickyUid = '';
  /// design/313 — one launch-destination apply per process, not on resume.
  bool _launchDestDone = false;
  late final AccessStickyStore _sticky =
      widget.accessSticky ?? PrefsAccessStickyStore();
  /// design/415 — link to the other window of this browser; null off the web.
  PaneLink? _pane;
  /// A spot that arrived before this figure window was allowed in.
  ({String cacheId, int si, int fi})? _paneWaiting;
  bool _paneAutoTried = false;
  Timer? _paneAutoTimer;
  bool _paneGesturePending = false;

  bool get _isFigurePane => _pane?.role == PaneRole.figure;

  /// design/420 — the figure window opens on its own once a paper opens. The
  /// wait outlasts one hello, so a figure window already open is not reloaded.
  void _armPaneAuto() {
    if (_pane?.role != PaneRole.main || _paneAutoTried) return;
    _paneAutoTimer?.cancel();
    _paneAutoTimer =
        Timer(kPaneBeat + const Duration(milliseconds: 600), _paneAutoOpen);
  }

  Future<void> _paneAutoOpen() async {
    final pane = _pane;
    if (!mounted || pane == null) return;
    final prefs = WebReadingPrefs.instance;
    await prefs.load();
    if (!mounted) return;
    if (!paneAutoOpenDue(
      enabled: prefs.autoFigurePane,
      role: pane.role,
      figureOpen: pane.figureOpen,
      hasPaper: widget.library.session?.isValid == true,
      tried: _paneAutoTried,
    )) {
      return;
    }
    _paneAutoTried = true;
    if (openFigurePane()) return;
    _paneGesturePending = true;
    openFigurePaneOnNextGesture(() {
      _paneGesturePending = false;
      return mounted && _pane?.figureOpen == false;
    });
    ScaffoldMessenger.maybeOf(context)?.showSnackBar(
      const SnackBar(
        content: Text(
          '그림 창은 화면을 한 번 누르면 열립니다. '
          '창 위쪽 오른쪽의 막힘 표시에서 팝업을 허용하면 다음부터 바로 열립니다.',
        ),
      ),
    );
  }

  void _goReader() {
    final hid = widget.library.takeOpenHandoffId();
    asrEvidenceBus?.record(
      'nav_surface',
      severity: 'lifecycle',
      stage: 'surface',
      details: {
        'surface': 'reader',
        if (hid != null && hid.isNotEmpty) 'handoff_id': hid,
      },
    );
    setState(() {
      _readerMounted = true;
      _readerSurface = true;
    });
    // design/415 — a paper opened here: the figure window opens it too.
    if (_pane?.role == PaneRole.main) {
      _sendPaneSpot();
      _armPaneAuto();
    }
  }

  void _goLibrary({bool recordLeft = true}) {
    if (_readerSurface && recordLeft) {
      unawaited(widget.library.recordReadLeft());
    }
    unawaited(widget.library.reloadResumeLabels());
    unawaited(widget.library.flushDocumentsMirrorCursors());
    asrEvidenceBus?.record(
      'nav_surface',
      severity: 'lifecycle',
      stage: 'surface',
      details: {'surface': 'library'},
    );
    setState(() => _readerSurface = false);
  }

  void _openSettings() {
    asrEvidenceBus?.record(
      'nav_settings_open',
      severity: 'lifecycle',
      stage: 'settings',
    );
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => SettingsScreen(
          theme: widget.theme,
          auth: widget.auth,
          shadowing: widget.shadowing,
          tts: widget.tts,
          translate: widget.translate,
          citePanel: widget.citePanel,
          library: widget.library,
        ),
      ),
    );
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    widget.auth.addListener(_onAuthChanged);
    // design/225 224b — soft-hide of open paper leaves reader surface.
    widget.library.onSoftHideOpened = () {
      if (!mounted) return;
      if (_readerSurface) {
        _goLibrary(recordLeft: false);
      }
    };
    // design/74 — FG notification tap → open that paper in reader.
    unawaited(widget.library.initUploadNotify());
    widget.library.uploadNotify.setOpenCacheIdHandler(_onNotifyOpenCacheId);
    unawaited(_consumePendingOpen());
    unawaited(_refreshAccessGate());
    // design/411 — reading spots follow between the devices of this account.
    widget.library.startSpotSync();
    _startPane();
    if (kIsWeb) unawaited(_startFullScreen());
  }

  /// design/422 — a new window would end full screen, so the figure window
  /// opens first and full screen takes the click after.
  Future<void> _startFullScreen() async {
    final prefs = WebReadingPrefs.instance;
    await prefs.load();
    if (!mounted || !prefs.fullScreen) return;
    enterFullScreenOnNextGesture(
      wanted: () => mounted && prefs.fullScreen,
      hold: () => fullScreenWaitsForPane(
        main: _pane?.role == PaneRole.main,
        autoPane: prefs.autoFigurePane,
        figureOpen: _pane?.figureOpen == true,
        tried: _paneAutoTried,
        gesturePending: _paneGesturePending,
      ),
    );
  }

  void _startPane() {
    final role = paneRoleFromUrl(Uri.base);
    if (role == null) return;
    final channel = openPaneChannel();
    if (channel == null) return;
    final id = '${DateTime.now().microsecondsSinceEpoch}-${identityHashCode(this)}';
    final link = PaneLink(channel: channel, role: role, windowId: id)
      ..onSpot = _onPaneSpot
      ..onSpotWanted = _sendPaneSpot
      ..needsSpot = (() => _accessUnlocked == true && widget.library.session == null)
      ..onMainGone = role == PaneRole.figure ? closeThisPaneWindow : null;
    _pane = link;
    widget.library.onSpotSaved = link.sendSpot;
    onPaneWindowClose(link.leave);
    link.start();
    if (role == PaneRole.main) unawaited(preparePaneScreens());
  }

  void _sendPaneSpot() {
    final s = widget.library.session;
    if (s == null || !s.isValid) return;
    _pane?.sendSpot(s.cacheId, s.sentenceIndex, s.figureIndex);
  }

  Future<void> _onPaneSpot(String cacheId, int si, int fi) async {
    if (!mounted) return;
    if (_accessUnlocked != true || !widget.auth.isLoggedIn) {
      if (_isFigurePane) _paneWaiting = (cacheId: cacheId, si: si, fi: fi);
      return;
    }
    final s = widget.library.session;
    if (s == null || !s.isValid || s.cacheId.trim() != cacheId.trim()) {
      // Only the figure window follows the main window to another paper.
      if (!_isFigurePane) return;
      final opened = await widget.library.openByCacheId(cacheId);
      if (!mounted || opened == null) return;
      if (!_readerSurface) _goReader();
    }
    await widget.library.followPane(cacheId, si, fi);
  }

  @override
  void dispose() {
    _accessRetry?.cancel();
    _paneAutoTimer?.cancel();
    widget.auth.removeListener(_onAuthChanged);
    WidgetsBinding.instance.removeObserver(this);
    widget.library.onSoftHideOpened = null;
    widget.library.uploadNotify.setOpenCacheIdHandler(null);
    widget.library.stopSpotSync();
    if (_pane != null) {
      widget.library.onSpotSaved = null;
      _pane!.dispose();
    }
    super.dispose();
  }

  void _armAccessRetry() {
    _accessRetry?.cancel();
    _accessRetry = Timer(const Duration(seconds: 8), () {
      if (!mounted || !widget.auth.isLoggedIn) return;
      unawaited(_refreshAccessGate());
    });
  }

  void _onAuthChanged() {
    if (!widget.auth.isLoggedIn) {
      // EDGE: logout must not leave previous user's unlocked shell / sticky.
      final uid = _stickyUid;
      if (uid.isNotEmpty) {
        unawaited(_sticky.clear(uid));
      }
      _stickyUid = '';
      _launchDestDone = false;
      _accessRetry?.cancel();
      setState(() {
        _accessUnlocked = null;
        _accessRestorePending = false;
      });
      return;
    }
    _stickyUid = widget.auth.user?.uid.trim() ?? '';
    unawaited(_refreshAccessGate());
  }

  Future<void> _refreshAccessGate() async {
    if (!widget.auth.isLoggedIn) {
      if (mounted) {
        setState(() {
          _accessUnlocked = null;
          _accessRestorePending = false;
        });
      }
      return;
    }
    final uid = widget.auth.user?.uid.trim() ?? '';
    if (uid.isNotEmpty) _stickyUid = uid;
    final sticky = uid.isEmpty ? null : await _sticky.readAllowed(uid);
    Object? lastErr;
    // Short retries before sticky path — same spirit as auth bootstrap.
    for (final delay in const <Duration>[
      Duration.zero,
      Duration(seconds: 2),
      Duration(seconds: 5),
    ]) {
      if (delay > Duration.zero) {
        await Future<void>.delayed(delay);
      }
      if (!mounted || !widget.auth.isLoggedIn) return;
      try {
        final st = await widget.auth.client.fetchAccessStatus();
        if (!mounted) return;
        final decided = resolveAccessUnlockOnFetch(
          fetchOk: true,
          statusUnlocked: accessUnlockedFromStatus(st),
          previousUnlocked: _accessUnlocked,
          stickyAllowed: sticky,
        );
        _accessRetry?.cancel();
        if (decided.writeStickyAllowed != null && uid.isNotEmpty) {
          unawaited(_sticky.writeAllowed(uid, decided.writeStickyAllowed!));
        }
        setState(() {
          _accessUnlocked = decided.unlocked;
          _accessRestorePending = false;
        });
        _armLaunchDestOnce();
        return;
      } catch (e) {
        lastErr = e;
      }
    }
    if (!mounted) return;
    final decided = resolveAccessUnlockOnFetch(
      fetchOk: false,
      previousUnlocked: _accessUnlocked,
      stickyAllowed: sticky,
    );
    asrEvidenceBus?.record(
      'client_api_timeout',
      severity: 'error',
      stage: 'access_status',
      message: (lastErr?.toString() ?? 'access_status_failed').length > 200
          ? (lastErr?.toString() ?? '').substring(0, 200)
          : (lastErr?.toString() ?? 'access_status_failed'),
      ok: false,
      details: {
        'route': 'access_status',
        'sticky_kept': decided.unlocked == true,
        'restore_pending': decided.restorePending,
      },
    );
    setState(() {
      _accessUnlocked = decided.unlocked;
      _accessRestorePending = decided.restorePending;
    });
    _armLaunchDestOnce();
    // Retry while sticky-kept or soft reconnect.
    if (decided.unlocked == true || decided.restorePending) {
      _armAccessRetry();
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // design/123 — persist sentence+figure on background/exit (product 5C).
    if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.inactive ||
        state == AppLifecycleState.detached) {
      unawaited(widget.library.persistOpenedProgress());
      unawaited(widget.library.flushSpots());
      unawaited(widget.library.recordReadLeft());
      unawaited(widget.bookmarks.pushToServer());
      if (state == AppLifecycleState.paused) {
        unawaited(asrEvidenceBus?.flush() ?? Future<void>.value());
      }
    }
    if (state == AppLifecycleState.resumed) {
      unawaited(_consumePendingOpen());
      unawaited(_resumeAfterInterrupt());
      unawaited(widget.shadowing.applyAutoOffIfStale());
      // design/84 — Allow may have happened while backgrounded.
      unawaited(_refreshAccessGate());
      // design/224 — wall-clock soft-delete purge after resume.
      unawaited(widget.library.purgeDueSoftDeletes());
      // design/250 — refresh focus/skill cloud cache.
      if (widget.auth.isLoggedIn) {
        unawaited(asrPracticeCloudSync?.ensurePulled(force: true));
      }
    }
  }

  Future<void> _resumeAfterInterrupt() async {
    if (!widget.auth.isLoggedIn) return;
    if (_accessUnlocked != true) return;
    final result = await widget.library.onAppResumed();
    if (!mounted || result == null) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('중단된 업로드를 이어서 처리합니다.')),
    );
  }

  Future<void> _onNotifyOpenCacheId(String cacheId) async {
    if (_accessUnlocked != true) return;
    final opened = await widget.library.openByCacheId(cacheId);
    if (!mounted) return;
    if (opened != null) {
      _goReader();
    }
  }

  Future<void> _consumePendingOpen() async {
    final id = await widget.library.uploadNotify.takePendingOpenCacheId();
    if (id == null || id.isEmpty) return;
    await _onNotifyOpenCacheId(id);
  }

  void _armLaunchDestOnce() {
    if (_launchDestDone || _accessUnlocked != true) return;
    if (!widget.auth.isLoggedIn) return;
    _launchDestDone = true;
    unawaited(_applyLaunchDest());
  }

  Future<void> _applyLaunchDest() async {
    if (!mounted || _accessUnlocked != true || !widget.auth.isLoggedIn) return;
    if (_readerSurface) return;
    // design/415 — the figure window shows what the main window has open, not the
    // last paper read.
    if (_isFigurePane) {
      final w = _paneWaiting;
      _paneWaiting = null;
      if (w != null) await _onPaneSpot(w.cacheId, w.si, w.fi);
      return;
    }
    await _consumePendingOpen();
    if (!mounted || _readerSurface) return;
    await widget.shadowing.applyAutoOffIfStale();
    try {
      await widget.library.refresh(trigger: 'launch_dest');
    } catch (_) {
      return;
    }
    if (!mounted || _readerSurface) return;
    final uid = widget.auth.user?.uid;
    final dest = await loadLaunchDest(uid);
    final live = widget.library.papers.map((p) => p.id).toSet();
    final open = resolveLaunchOpen(
      dest: dest,
      shadowingOn:
          widget.shadowing.enabled && widget.shadowing.serverAvailable,
      readAt: await loadReadAtByCacheId(uid),
      practiceAt: await loadPracticeAtByCacheId(uid),
      liveIds: live,
    );
    if (open == null || !mounted || _readerSurface) return;
    final opened = await widget.library.openByCacheId(open.cacheId);
    if (!mounted || opened == null || _readerSurface) return;
    _goReader();
    if (!open.practice) return;
    await widget.shadowing.recordPracticePressed();
    if (!mounted) return;
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => ShadowingPracticeScreen(
          client: widget.auth.client,
          library: widget.library,
          shadowing: widget.shadowing,
          tts: widget.tts,
        ),
      ),
    );
    unawaited(widget.library.reloadResumeLabels());
  }

  Widget _padded(Widget child) {
    return SafeArea(
      bottom: false,
      child: Padding(
        padding: const EdgeInsets.only(top: 8),
        child: child,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: Listenable.merge([
        widget.auth,
        widget.library,
        widget.tts,
        widget.theme,
        widget.bookmarks,
      ]),
      builder: (context, _) {
        final auth = widget.auth;

        if (auth.bootstrapping) {
          return const Scaffold(
            body: Center(child: CircularProgressIndicator()),
          );
        }

        // 0.3.123 — cookie kept after auth timeout; do not bounce to LoginScreen.
        if (auth.sessionRestorePending) {
          return Scaffold(
            body: _padded(
              Center(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const CircularProgressIndicator(),
                      const SizedBox(height: 16),
                      Text(
                        auth.error ?? '서버 연결 중…',
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 16),
                      FilledButton(
                        onPressed: auth.busy
                            ? null
                            : () => unawaited(auth.bootstrap()),
                        child: const Text('다시 시도'),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          );
        }

        // design/83 — identity gate first.
        if (!auth.isLoggedIn && auth.loginRequired) {
          return Scaffold(
            body: _padded(LoginScreen(auth: auth)),
          );
        }

        // design/84 · 172 — invite waiting / soft reconnect after login.
        if (auth.isLoggedIn) {
          if (_accessRestorePending) {
            return Scaffold(
              body: _padded(
                Center(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 24),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const CircularProgressIndicator(),
                        const SizedBox(height: 16),
                        const Text(
                          '서버 연결이 느립니다. 액세스 상태를 다시 확인합니다.',
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 16),
                        FilledButton(
                          onPressed: () => unawaited(_refreshAccessGate()),
                          child: const Text('다시 시도'),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            );
          }
          if (_accessUnlocked == null) {
            return const Scaffold(
              body: Center(child: CircularProgressIndicator()),
            );
          }
          if (_accessUnlocked == false) {
            return Scaffold(
              body: _padded(
                AccessWaitingScreen(
                  auth: auth,
                  onUnlocked: () {
                    final uid = auth.user?.uid.trim() ?? '';
                    if (uid.isNotEmpty) {
                      unawaited(_sticky.writeAllowed(uid, true));
                    }
                    if (mounted) {
                      setState(() {
                        _accessUnlocked = true;
                        _accessRestorePending = false;
                      });
                      _armLaunchDestOnce();
                    }
                  },
                ),
              ),
            );
          }
        }

        final Widget libraryPage = _isFigurePane
            ? const Center(
                child: Padding(
                  padding: EdgeInsets.all(24),
                  child: Text(
                    '그림 창입니다.\n문장 창에서 논문을 열면 여기에 그림이 나옵니다.',
                    textAlign: TextAlign.center,
                  ),
                ),
              )
            : LibraryScreen(
                auth: widget.auth,
                library: widget.library,
                bookmarks: widget.bookmarks,
                annotations: widget.annotations,
                shadowing: widget.shadowing,
                tts: widget.tts,
                onOpened: _goReader,
                onOpenSettings: _openSettings,
              );
        final readerPage = ReaderScreen(
          library: widget.library,
          tts: widget.tts,
          client: widget.auth.client,
          shadowing: widget.shadowing,
          translate: widget.translate,
          citePanel: widget.citePanel,
          bookmarks: widget.bookmarks,
          annotations: widget.annotations,
          pane: _pane,
          onBack: _isFigurePane ? null : _goLibrary,
        );

        // design/224 — no bottom tabs; reader Offstage keep-alive (P1).
        return PopScope(
          canPop: !_readerSurface,
          onPopInvokedWithResult: (didPop, _) {
            if (didPop) return;
            if (_readerSurface) {
              _goLibrary();
            }
          },
          child: Scaffold(
            body: _padded(
              Stack(
                children: [
                  Offstage(
                    offstage: _readerSurface,
                    child: TickerMode(
                      enabled: !_readerSurface,
                      child: libraryPage,
                    ),
                  ),
                  if (_readerMounted)
                    Offstage(
                      offstage: !_readerSurface,
                      child: TickerMode(
                        enabled: _readerSurface,
                        child: readerPage,
                      ),
                    ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}
