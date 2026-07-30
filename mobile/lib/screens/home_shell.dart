import 'package:flutter/material.dart';

import '../state/auth_controller.dart';
import 'library_screen.dart';
import 'login_screen.dart';
import 'reader_screen.dart';
import 'status_screen.dart';

/// Bottom-nav shell: Status · Login · Library · Reader.
class HomeShell extends StatefulWidget {
  const HomeShell({super.key, required this.auth});

  final AuthController auth;

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;

  static const _titles = ['서버', '로그인', '보관', '읽기'];

  @override
  Widget build(BuildContext context) {
    final pages = <Widget>[
      const StatusScreen(),
      LoginScreen(auth: widget.auth),
      const LibraryScreen(),
      const ReaderScreen(),
    ];

    return AnimatedBuilder(
      animation: widget.auth,
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
            ],
          ),
        );
      },
    );
  }
}
