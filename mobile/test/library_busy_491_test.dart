import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sentence_reading/api/client.dart';
import 'package:sentence_reading/api/session_store.dart';
import 'package:sentence_reading/api/upload_draft_store.dart';
import 'package:sentence_reading/api/upload_reserve_models.dart';
import 'package:sentence_reading/screens/library_screen.dart';
import 'package:sentence_reading/state/auth_controller.dart';
import 'package:sentence_reading/state/bookmark_controller.dart';
import 'package:sentence_reading/state/library_controller.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _hashB = 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory dir;

  setUp(() {
    SharedPreferences.setMockInitialValues({});
    dir = Directory.systemTemp.createTempSync('library_busy_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (call) async => dir.path,
    );
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
    try {
      dir.deleteSync(recursive: true);
    } catch (_) {}
  });

  Future<({AuthController auth, LibraryController lib, List<String> opened})> boot(
    WidgetTester tester,
  ) async {
    final opened = <String>[];
    final mock = MockClient((request) async {
      final path = request.url.path;
      if (path.endsWith('/api/auth/status')) {
        return http.Response(
          '{"ok":true,"auth_enabled":true,"providers":{"email":true},"user":{"uid":"u1","email":"a@b.c","providers":["email"]}}',
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (path.endsWith('/api/cache/papers')) {
        return http.Response(
          '{"ok":true,"papers":['
          '{"id":"c1","title":"First Paper About Nickel Copper Alloys","sentence_count":3},'
          '{"id":"c2","title":"Second Paper About Methane Reforming Work","sentence_count":3,"content_hash":"$_hashB"}'
          ']}',
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      }
      if (path.endsWith('/open')) {
        opened.add(path);
        return http.Response('{"ok":false,"error":"nope"}', 404);
      }
      return http.Response('{}', 404);
    });
    final store = MemorySessionStore();
    await store.writeToken('tok');
    final client = AsrClient(httpClient: mock, sessionStore: store);
    final auth = AuthController(client: client);
    final lib = LibraryController(client: client, draftStore: MemoryUploadDraftStore());
    await tester.runAsync(() => auth.bootstrap());
    await tester.runAsync(() => lib.refresh());
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: LibraryScreen(
          auth: auth,
          library: lib,
          bookmarks: BookmarkController(client: client),
        ),
      ),
    ));
    await tester.pump();
    return (auth: auth, lib: lib, opened: opened);
  }

  testWidgets('design/491 another card opens while an upload runs', (tester) async {
    final b = await boot(tester);
    b.lib.uploading = true;
    b.lib.notifyListeners();
    await tester.pump();
    await tester.runAsync(() async {
      await tester.tap(find.text('First Paper About Nickel Copper Alloys'));
      await Future<void>.delayed(const Duration(milliseconds: 200));
    });
    await tester.pump();
    expect(b.opened, ['/api/cache/papers/c1/open']);
  });

  testWidgets('design/491 the card being reanalysed says so and does not open', (tester) async {
    final b = await boot(tester);
    b.lib.reanalyzing = true;
    b.lib.reanalyzingCacheId = 'c2';
    b.lib.notifyListeners();
    await tester.pump();
    expect(b.lib.busyCacheIds, {'c2'});
    await tester.tap(find.text('Second Paper About Methane Reforming Work'));
    await tester.pump();
    expect(find.text(kBusyCardNote), findsOneWidget);
    expect(b.opened, isEmpty);
  });

  testWidgets('design/491 an upload of the same file marks that card busy', (tester) async {
    final b = await boot(tester);
    b.lib.uploading = true;
    b.lib.uploadQueue = [
      UploadReserveItem(
        contentHash: _hashB,
        filename: 'b.pdf',
        localPath: '/x/b.pdf',
        bytesLen: 10,
        status: 'active',
        enqueuedAtMs: 1,
      ),
    ];
    expect(b.lib.busyCacheIds, {'c2'});
    b.lib.uploading = false;
    expect(b.lib.busyCacheIds, isEmpty);
  });
}
