import 'package:flutter/material.dart';

import '../state/auth_controller.dart';
import '../state/library_controller.dart';
import '../state/theme_controller.dart';
import '../state/tts_controller.dart';
import 'library_screen.dart';
import 'login_screen.dart';
import 'reader_screen.dart';
import 'settings_screen.dart';
import 'status_screen.dart';

/// Bottom-nav shell: Status · Login · Library · Reader · Settings.
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

class _HomeShellState extends State<HomeShell> {
  int _index = 0;

  static const _titles = ['서버', '로그인', '보관', '읽기', '설정'];

  void _goReader() => setState(() => _index = 3);

  @override
  Widget build(BuildContext context) {
    final pages = <Widget>[
      const StatusScreen(),
      LoginScreen(auth: widget.auth),
      LibraryScreen(
        auth: widget.auth,
        library: widget.library,
        onOpened: _goReader,
      ),
      ReaderScreen(library: widget.library, tts: widget.tts),
      SettingsScreen(theme: widget.theme, auth: widget.auth),
    ];

    return AnimatedBuilder(
      animation: Listenable.merge([
        widget.auth,
        widget.library,
        widget.tts,
        widget.theme,
      ]),
      builder: (context, _) {
        final logged = widget.auth.isLoggedIn;
        final titleExtra = logged ? ' · ${widget.auth.user!.displayLabel}' : '';
        return Scaffold(
          appBar: AppBar(
            title: Text('문장 읽기 · ${_titles[_index]}$titleExtra'),
          ),
          body: IndexedStack(index: _index, children: pages),
          bottomNavigationBar: NavigationBar(
            selectedIndex: _index,
            onDestinationSelected: (i) => setState(() => _index = i),
            destinations: [
              const NavigationDestination(
                icon: Icon(Icons.cloud_outlined),
                label: '서버',
              ),
              NavigationDestination(
                icon: Icon(logged ? Icons.person_outline : Icons.login),
                label: logged ? '계정' : '로그인',
              ),
              const NavigationDestination(
                icon: Icon(Icons.library_books_outlined),
                label: '보관',
              ),
              const NavigationDestination(
                icon: Icon(Icons.menu_book_outlined),
                label: '읽기',
              ),
              const NavigationDestination(
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
