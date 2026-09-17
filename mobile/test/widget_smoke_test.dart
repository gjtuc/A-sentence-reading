import 'dart:io';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sentence_reading/api/client.dart';
import 'package:sentence_reading/api/session_store.dart';
import 'package:sentence_reading/app.dart';
import 'package:sentence_reading/state/auth_controller.dart';
import 'package:sentence_reading/state/library_controller.dart';
import 'package:sentence_reading/state/tts_controller.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Building the app shell reaches prefs, the documents directory, and the audio
/// player. None of those plugins exist under `flutter test`, so stub them.
/// A player id the test controls, so its event channel can be stubbed by name.
const String kSmokePlayerId = 'asr-smoke-player';

void _stubPlatformChannels() {
  SharedPreferences.setMockInitialValues({});
  final dir = Directory.systemTemp.createTempSync('asr_smoke');
  addTearDown(() {
    try {
      dir.deleteSync(recursive: true);
    } on FileSystemException {
      // EDGE: Windows may still hold a handle; a leftover temp dir is harmless.
    }
  });
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  messenger.setMockMethodCallHandler(
    const MethodChannel('plugins.flutter.io/path_provider'),
    (call) async => dir.path,
  );
  // TtsController builds an AudioPlayer as soon as the app shell is created.
  for (final name in <String>[
    'xyz.luan/audioplayers',
    'xyz.luan/audioplayers.global',
  ]) {
    messenger.setMockMethodCallHandler(MethodChannel(name), (call) async => null);
  }
  for (final name in <String>[
    'xyz.luan/audioplayers.global/events',
    'xyz.luan/audioplayers/events/$kSmokePlayerId',
  ]) {
    messenger.setMockStreamHandler(
      EventChannel(name),
      MockStreamHandler.inline(onListen: (arguments, sink) {}),
    );
  }
}

void main() {
  testWidgets('login gate then library lists papers when authenticated',
      (tester) async {
    _stubPlatformChannels();
    var loggedIn = false;
    final mock = MockClient((request) async {
      final path = request.url.path;
      if (path.endsWith('/api/auth/status')) {
        if (loggedIn) {
          return http.Response(
            '{"ok":true,"auth_enabled":true,"providers":{"email":true},"user":{"uid":"u1","email":"a@b.c","providers":["email"]}}',
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response(
          '{"ok":true,"auth_enabled":true,"providers":{"email":true},"user":null}',
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (path.endsWith('/api/cache/papers')) {
        return http.Response(
          '{"ok":true,"papers":[{"id":"c1","title":"Sample Paper","source":"pdf","sentence_count":10,"figure_count":1,"updated_at":"2026-07-01"}]}',
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (path.endsWith('/api/status')) {
        return http.Response(
          '{"ok":true,"version":"0.2.87","pipeline":"rich-v7","mobile_library":true,"mobile_shell_nav":true,"mobile_upload":true}',
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      // WHY: SettingsScreen (IndexedStack) may call access APIs after login.
      // EDGE: missing mock → 404 noise / incomplete settle; not a success path.
      // design/67 — an approved user must reach the library, not the waiting shell.
      if (path.endsWith('/api/access/status')) {
        return http.Response(
          '{"ok":true,"gate_enabled":true,"invite_pool_ready":true,"status":"allowed","effective":"allowed","can_use_paid":true,"is_admin":false,"invited_at":null,"decided_at":null,"decision_note":"","code_format":"XXXX-XXXX"}',
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (path.contains('/api/access/admin/')) {
        return http.Response(
          '{"ok":false,"error":"admin_required","message":"admin only"}',
          403,
          headers: {'content-type': 'application/json'},
        );
      }
      return http.Response('{}', 404);
    });
    final store = MemorySessionStore();
    final client = AsrClient(httpClient: mock, sessionStore: store);
    final auth = AuthController(client: client);
    final library = LibraryController(client: client);
    // WHY: bootstrap awaits platform channels (deep links, prefs). Under the
    // fake clock those replies never arrive without a pump, so a plain await
    // deadlocked this test for 10 minutes until it timed out.
    await tester.runAsync(() => auth.bootstrap());

    final tts = TtsController(
      client: client,
      library: library,
      player: AudioPlayer(playerId: kSmokePlayerId),
    );
    await tester.pumpWidget(
      SentenceReadingApp(auth: auth, library: library, tts: tts),
    );
    await tester.pump();

    // WHY (design/68): the logged-out shell is login-only — no library behind it.
    expect(find.text('Sample Paper'), findsNothing);
    expect(find.text('로그인'), findsWidgets);
    // Only the email provider is enabled in this mock, and design/77 makes
    // email sign-in a magic link rather than a password form.
    expect(find.text('이메일로 로그인 링크 받기'), findsOneWidget);

    // Simulate login by writing session + re-bootstrap with user.
    loggedIn = true;
    await store.writeToken('tok');
    await tester.runAsync(() => auth.bootstrap());
    await tester.pump();
    await tester.runAsync(() => library.refresh());
    await tester.pump();

    expect(find.text('Sample Paper'), findsOneWidget);
  });
}

