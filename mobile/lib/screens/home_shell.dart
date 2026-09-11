import 'dart:async';

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
import '../services/evidence_bus.dart';
import 'access_waiting_screen.dart';
import 'library_screen.dart';
import 'login_screen.dart';
import 'reader_screen.dart';
import 'settings_screen.dart';

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
  late final AccessStickyStore _sticky =
      widget.accessSticky ?? PrefsAccessStickyStore();

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
  }

  void _goLibrary({bool recordLeft = true}) {
    if (_readerSurface && recordLeft) {
      unawaited(widget.library.recordReadLeft());
    }
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
  }

  @override
  void dispose() {
    _accessRetry?.cancel();
    widget.auth.removeListener(_onAuthChanged);
    WidgetsBinding.instance.removeObserver(this);
    widget.library.onSoftHideOpened = null;
    widget.library.uploadNotify.setOpenCacheIdHandler(null);
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
      unawaited(widget.library.recordReadLeft());
      unawaited(widget.bookmarks.pushToServer());
    }
    if (state == AppLifecycleState.resumed) {
      unawaited(_consumePendingOpen());
      unawaited(_resumeAfterInterrupt());
      unawaited(widget.shadowing.applyAutoOffIfStale());
      // design/84 — Allow may have happened while backgrounded.
      unawaited(_refreshAccessGate());
      // design/224 — wall-clock soft-delete purge after resume.
      unawaited(widget.library.purgeDueSoftDeletes());
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
                    }
                  },
                ),
              ),
            );
          }
        }

        final libraryPage = LibraryScreen(
          auth: widget.auth,
          library: widget.library,
          bookmarks: widget.bookmarks,
          annotations: widget.annotations,
          shadowing: widget.shadowing,
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
