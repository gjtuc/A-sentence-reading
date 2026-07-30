import 'package:flutter/material.dart';

import 'screens/home_shell.dart';
import 'state/auth_controller.dart';
import 'state/library_controller.dart';

/// Root Material app — brand title 「문장 읽기」.
class SentenceReadingApp extends StatefulWidget {
  const SentenceReadingApp({super.key, this.auth, this.library});

  /// Optional inject for tests (memory session / fake client).
  final AuthController? auth;
  final LibraryController? library;

  @override
  State<SentenceReadingApp> createState() => _SentenceReadingAppState();
}

class _SentenceReadingAppState extends State<SentenceReadingApp> {
  late final AuthController _auth = widget.auth ?? AuthController();
  late final LibraryController _library =
      widget.library ?? LibraryController(client: _auth.client);
  @override
  void initState() {
    super.initState();
    _auth.bootstrap();
  }

  @override
  void dispose() {
    if (widget.auth == null) {
      _auth.dispose();
    }
    // LibraryController does not own the client.
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '문장 읽기',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF1B4F72)),
        useMaterial3: true,
      ),
      home: HomeShell(auth: _auth, library: _library),
    );
  }
}
