import 'dart:async';

import 'package:flutter/material.dart';

import '../state/auth_controller.dart';
import '../state/library_controller.dart';
import '../state/shadowing_controller.dart';
import '../state/theme_controller.dart';
import '../state/translate_controller.dart';
import '../state/tts_controller.dart';
import 'access_waiting_screen.dart';
import 'library_screen.dart';
import 'login_screen.dart';
import 'reader_screen.dart';
import 'settings_screen.dart';

/// Auth-gated shell (design/68) + access waiting (design/84).
///
/// Logged out → login only (no bottom nav).
/// Logged in · invite pending/denied → waiting only.
/// Allowed / gate off → 보관 · 읽기 · 설정.
class HomeShell extends StatefulWidget {
  const HomeShell({
    super.key,
    required this.auth,
    required this.library,
    required this.tts,
    required this.theme,
    required this.shadowing,
    required this.translate,
  });

  final AuthController auth;
  final LibraryController library;
  final TtsController tts;
  final ThemeController theme;
  final ShadowingController shadowing;
  final TranslateController translate;

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> with WidgetsBindingObserver {
  int _index = 0;
  /// null = not checked yet; true = may enter main tabs.
  bool? _accessUnlocked;

  void _goReader() => setState(() => _index = 1);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    widget.auth.addListener(_onAuthChanged);
    // design/74 — FG notification tap → open that paper in reader.
    unawaited(widget.library.initUploadNotify());
    widget.library.uploadNotify.setOpenCacheIdHandler(_onNotifyOpenCacheId);
    unawaited(_consumePendingOpen());
    unawaited(_refreshAccessGate());
  }

  @override
  void dispose() {
    widget.auth.removeListener(_onAuthChanged);
    WidgetsBinding.instance.removeObserver(this);
    widget.library.uploadNotify.setOpenCacheIdHandler(null);
    super.dispose();
  }

  void _onAuthChanged() {
    if (!widget.auth.isLoggedIn) {
      // EDGE: logout must not leave previous user's unlocked shell.
      setState(() => _accessUnlocked = null);
      return;
    }
    unawaited(_refreshAccessGate());
  }

  Future<void> _refreshAccessGate() async {
    if (!widget.auth.isLoggedIn) {
      if (mounted) setState(() => _accessUnlocked = null);
      return;
    }
    try {
      final st = await widget.auth.client.fetchAccessStatus();
      if (!mounted) return;
      // WHY: gate off or can_use_paid → main app; else waiting-only.
      setState(() => _accessUnlocked = !st.gateEnabled || st.canUsePaid);
    } catch (_) {
      if (!mounted) return;
      // FAIL-CLOSED: unknown access → waiting screen (retry via poll), not main app.
      setState(() => _accessUnlocked = false);
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(_consumePendingOpen());
      unawaited(_resumeAfterInterrupt());
      // design/84 — Allow may have happened while backgrounded.
      unawaited(_refreshAccessGate());
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
      ]),
      builder: (context, _) {
        final auth = widget.auth;

        if (auth.bootstrapping) {
          return const Scaffold(
            body: Center(child: CircularProgressIndicator()),
          );
        }

        // design/83 — identity gate first.
        if (!auth.isLoggedIn && auth.loginRequired) {
          return Scaffold(
            body: _padded(LoginScreen(auth: auth)),
          );
        }

        // design/84 — invite waiting after login.
        if (auth.isLoggedIn) {
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
                    if (mounted) setState(() => _accessUnlocked = true);
                  },
                ),
              ),
            );
          }
        }

        final pages = <Widget>[
          LibraryScreen(
            auth: widget.auth,
            library: widget.library,
            onOpened: _goReader,
          ),
          ReaderScreen(
            library: widget.library,
            tts: widget.tts,
            client: widget.auth.client,
            shadowing: widget.shadowing,
            translate: widget.translate,
          ),
          SettingsScreen(
            theme: widget.theme,
            auth: widget.auth,
            shadowing: widget.shadowing,
            tts: widget.tts,
            translate: widget.translate,
            library: widget.library,
          ),
        ];

        return Scaffold(
          body: _padded(IndexedStack(index: _index, children: pages)),
          bottomNavigationBar: NavigationBar(
            selectedIndex: _index,
            onDestinationSelected: (i) => setState(() => _index = i),
            destinations: const [
              NavigationDestination(
                icon: Icon(Icons.library_books_outlined),
                label: '보관',
              ),
              NavigationDestination(
                icon: Icon(Icons.menu_book_outlined),
                label: '읽기',
              ),
              NavigationDestination(
                icon: Icon(Icons.settings_outlined),
                label: '설정',
              ),
            ],
          ),
        );
      },
    );
  }
}
