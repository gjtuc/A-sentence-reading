import 'dart:async';

import 'package:flutter/material.dart';

import '../state/auth_controller.dart';
import '../state/library_controller.dart';
import '../state/theme_controller.dart';
import '../state/tts_controller.dart';
import 'library_screen.dart';
import 'login_screen.dart';
import 'reader_screen.dart';
import 'settings_screen.dart';

/// Auth-gated shell (design/68).
///
/// Logged out → login only (no bottom nav).
/// Logged in → 보관 · 읽기 · 설정. Account/server live under Settings.
class HomeShell extends StatefulWidget {
  const HomeShell({
    super.key,
    required this.auth,
    required this.library,
    required this.tts,
    required this.theme,
  });

  final AuthController auth;
  final LibraryController library;
  final TtsController tts;
  final ThemeController theme;

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> with WidgetsBindingObserver {
  int _index = 0;

  void _goReader() => setState(() => _index = 1);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    // design/74 — FG notification tap → open that paper in reader.
    unawaited(widget.library.initUploadNotify());
    widget.library.uploadNotify.setOpenCacheIdHandler(_onNotifyOpenCacheId);
    unawaited(_consumePendingOpen());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    widget.library.uploadNotify.setOpenCacheIdHandler(null);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(_consumePendingOpen());
    }
  }

  Future<void> _onNotifyOpenCacheId(String cacheId) async {
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
    // WHY: no AppBar — SafeArea + small top pad (user preferred vs full toolbar gap).
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

        // EDGE: session restore in flight — do not flash tabs or login form.
        if (auth.bootstrapping) {
          return const Scaffold(
            body: Center(child: CircularProgressIndicator()),
          );
        }

        // WHY: without login, library/reader/settings are unusable — gate first.
        // EDGE: fail-closed — no bottom nav until session exists.
        if (!auth.isLoggedIn) {
          return Scaffold(
            body: _padded(LoginScreen(auth: auth)),
          );
        }

        final pages = <Widget>[
          LibraryScreen(
            auth: widget.auth,
            library: widget.library,
            onOpened: _goReader,
          ),
          ReaderScreen(library: widget.library, tts: widget.tts),
          SettingsScreen(theme: widget.theme, auth: widget.auth),
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
