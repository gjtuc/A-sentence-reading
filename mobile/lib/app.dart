import 'package:flutter/material.dart';

import 'screens/home_shell.dart';
import 'state/auth_controller.dart';
import 'state/library_controller.dart';
import 'state/shadowing_controller.dart';
import 'state/theme_controller.dart';
import 'state/translate_controller.dart';
import 'state/tts_controller.dart';

/// Root Material app — brand title 「문장 읽기」.
class SentenceReadingApp extends StatefulWidget {
  const SentenceReadingApp({
    super.key,
    this.auth,
    this.library,
    this.tts,
    this.theme,
    this.shadowing,
    this.translate,
  });

  /// Optional inject for tests (memory session / fake client).
  final AuthController? auth;
  final LibraryController? library;
  final TtsController? tts;
  final ThemeController? theme;
  final ShadowingController? shadowing;
  final TranslateController? translate;

  @override
  State<SentenceReadingApp> createState() => _SentenceReadingAppState();
}

class _SentenceReadingAppState extends State<SentenceReadingApp> {
  late final AuthController _auth = widget.auth ?? AuthController();
  late final LibraryController _library =
      widget.library ?? LibraryController(client: _auth.client);
  late final TtsController _tts =
      widget.tts ?? TtsController(client: _auth.client, library: _library);
  late final ThemeController _theme = widget.theme ?? ThemeController();
  late final ShadowingController _shadowing =
      widget.shadowing ?? ShadowingController();
  late final TranslateController _translate =
      widget.translate ?? TranslateController();

  static const _seed = Color(0xFF1B4F72);

  @override
  void initState() {
    super.initState();
    _auth.bootstrap();
    _theme.bootstrap();
    _tts.bootstrap();
    _auth.addListener(_onAuthPrefs);
    _syncPrefsFromAuth();
  }

  void _onAuthPrefs() => _syncPrefsFromAuth();

  Future<void> _syncPrefsFromAuth() async {
    if (!_auth.isLoggedIn || _auth.user == null) {
      _shadowing.clearSession();
      _shadowing.setServerAvailable(false);
      _translate.clearSession();
      return;
    }
    await _shadowing.bindUid(_auth.user!.uid);
    await _translate.bindUid(_auth.user!.uid);
    try {
      final st = await _auth.client.fetchStatus();
      _shadowing.setServerAvailable(st.mobileShadowingPractice);
    } catch (_) {
      // EDGE: status fail → keep kill closed (no false enable).
      _shadowing.setServerAvailable(false);
    }
  }

  @override
  void dispose() {
    _auth.removeListener(_onAuthPrefs);
    if (widget.auth == null) {
      _auth.dispose();
    }
    // LibraryController does not own the client.
    if (widget.tts == null) {
      _tts.dispose();
    }
    // Theme / Shadowing / Translate have no owned client.
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _theme,
      builder: (context, _) {
        return MaterialApp(
          title: '문장 읽기',
          debugShowCheckedModeBanner: false,
          themeMode: _theme.mode,
          theme: ThemeData(
            colorScheme: ColorScheme.fromSeed(
              seedColor: _seed,
              brightness: Brightness.light,
            ),
            useMaterial3: true,
          ),
          darkTheme: ThemeData(
            colorScheme: ColorScheme.fromSeed(
              seedColor: _seed,
              brightness: Brightness.dark,
            ),
            useMaterial3: true,
          ),
          home: HomeShell(
            auth: _auth,
            library: _library,
            tts: _tts,
            theme: _theme,
            shadowing: _shadowing,
            translate: _translate,
          ),
        );
      },
    );
  }
}
