import 'package:flutter/material.dart';

import 'library_screen.dart';
import 'login_screen.dart';
import 'reader_screen.dart';
import 'status_screen.dart';

/// Bottom-nav shell: Status · Login · Library · Reader (placeholders until auth MVP).
class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

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
      const LoginScreen(),
      const LibraryScreen(),
      const ReaderScreen(),
    ];

    return Scaffold(
      appBar: AppBar(title: Text('문장 읽기 · ${_titles[_index]}')),
      body: IndexedStack(index: _index, children: pages),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.cloud_outlined), label: '서버'),
          NavigationDestination(icon: Icon(Icons.login), label: '로그인'),
          NavigationDestination(icon: Icon(Icons.library_books_outlined), label: '보관'),
          NavigationDestination(icon: Icon(Icons.menu_book_outlined), label: '읽기'),
        ],
      ),
    );
  }
}
