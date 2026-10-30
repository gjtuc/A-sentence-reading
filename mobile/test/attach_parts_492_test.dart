import 'dart:convert';
import 'dart:io';

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sentence_reading/api/client.dart';
import 'package:sentence_reading/api/doc_parts.dart';
import 'package:sentence_reading/api/paper_models.dart';
import 'package:sentence_reading/api/reader_nav_labels.dart';
import 'package:sentence_reading/api/session_store.dart';
import 'package:sentence_reading/api/upload_draft_store.dart';
import 'package:sentence_reading/screens/library_screen.dart';
import 'package:sentence_reading/services/paper_disk_store.dart';
import 'package:sentence_reading/state/auth_controller.dart';
import 'package:sentence_reading/state/bookmark_controller.dart';
import 'package:sentence_reading/state/library_controller.dart';
import 'package:sentence_reading/widgets/attach_dialogs.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _title =
    'Platinum single atom catalyst coupled with transition metal oxide heterostructure';

PaperEntry _row(
  String id, {
  String title = _title,
  String role = 'main',
  String kind = 'paper',
  String name = '',
  String paired = '',
  bool canMerge = false,
}) =>
    PaperEntry(
      id: id,
      title: title,
      docRole: role,
      docKind: kind,
      sourceName: name,
      pairedCacheId: paired,
      canMergeSupplementary: canMerge,
    );

void main() {
  test('design/492 file number links a Nature paper, its SI and review file', () {
    final k = fileArticleKey('s41467-021-24079-8.pdf');
    expect(k, 'n:41467-21-24079');
    expect(fileArticleKey('41467_2021_24079_MOESM1_ESM.pdf'), k);
    expect(fileArticleKey('C:\\dl\\41467_2021_24079_MOESM2_ESM.pdf'), k);
    expect(
      fileArticleKey('1-s2.0-S0360319921012345-main.pdf'),
      fileArticleKey('1-s2.0-S0360319921012345-mmc1.pdf'),
    );
    expect(fileArticleKey('ja1c01234_si_001.pdf'), fileArticleKey('ja1c01234.pdf'));
    expect(fileArticleKey('paper.pdf'), '');
    expect(fileArticleKey('main.pdf'), '');
  });

  test('design/492 the paper takes in its paired SI, then the review file', () {
    final out = applyFileKeyParts([
      _row('m', name: 's41467-021-24079-8.pdf', paired: 'si', canMerge: true),
      _row('rv', title: 'REVIEWER COMMENTS', kind: 'review',
          name: '41467_2021_24079_MOESM2_ESM.pdf'),
      _row('si', role: 'supplementary', name: '41467_2021_24079_MOESM1_ESM.pdf',
          paired: 'm'),
    ]);
    expect(out[0].mergePartIds, ['si', 'rv']);
    expect(out[1].mergePartIds, isEmpty);
    expect(out[2].mergePartIds, isEmpty);
  });

  test('design/492 two papers on one number link nothing; another SI stays put', () {
    final two = applyFileKeyParts([
      _row('a', name: 'ab123456.pdf'),
      _row('b', name: 'ab123456-main.pdf', title: 'Another paper title here'),
      _row('rv', kind: 'review', name: 'ab123456_review.pdf'),
    ]);
    expect(two.every((e) => e.mergePartIds.isEmpty), isTrue);
    final taken = applyFileKeyParts([
      _row('a', name: 'ab123456.pdf'),
      _row('si', role: 'supplementary', name: 'ab123456_si.pdf', paired: 'z'),
    ]);
    expect(taken.first.mergePartIds, isEmpty);
  });

  test('design/492 merged tags, server rows and section names', () {
    expect(mergedTagFor(const []), '메인+서플먼터리');
    expect(mergedTagFor(const ['supplementary']), '메인+서플먼터리');
    expect(mergedTagFor(const ['supplementary', 'review']), '메인+보충+심사');
    final e = PaperEntry.fromJson({
      'id': 'm',
      'title': _title,
      'doc_role': 'merged',
      'merged_sections': ['supplementary', 'review'],
      'source_name': 'x/s41467-021-24079-8.pdf',
    });
    expect(e.libraryTag, '메인+보충+심사');
    expect(e.sourceName, 's41467-021-24079-8.pdf');
    expect(sectionDisplayName('review'), 'Peer review');
    expect(sectionDisplayName('attached'), 'Attached');
    final parts = orderParts([
      _row('x', kind: 'general'),
      _row('rv', kind: 'review'),
      _row('si', role: 'supplementary'),
    ]);
    expect([for (final p in parts) p.id], ['si', 'rv', 'x']);
  });

  test('design/492 index rows keep the file name and merged sections', () {
    final row = PaperDiskIndexEntry(
      id: 'm',
      title: _title,
      docRole: 'merged',
      sourceName: 's41467-021-24079-8.pdf',
      mergedSections: const ['supplementary', 'review'],
    );
    final back = PaperDiskIndexEntry.fromJson(row.toJson());
    expect(back.sourceName, 's41467-021-24079-8.pdf');
    expect(back.mergedSections, ['supplementary', 'review']);
    expect(back.toPaperEntry().libraryTag, '메인+보충+심사');
    final later = PaperDiskIndexEntry(id: 'm', title: _title, docRole: 'merged')
        .keepingFrom(back);
    expect(later.sourceName, 's41467-021-24079-8.pdf');
    expect(later.mergedSections, ['supplementary', 'review']);
  });

  test('design/492 attach targets: same file number, then same title', () {
    final part = _row('rv', title: 'REVIEWER COMMENTS', kind: 'review',
        name: '41467_2021_24079_MOESM2_ESM.pdf');
    final targets = attachTargetsFor(part, [
      _row('other', title: 'Some unrelated paper about batteries'),
      _row('si', role: 'supplementary'),
      _row('m', name: 's41467-021-24079-8.pdf'),
      part,
    ]);
    expect([for (final t in targets) t.id], ['m', 'other']);
  });

  group('design/492 library card', () {
    late Directory dir;

    setUp(() {
      SharedPreferences.setMockInitialValues({});
      dir = Directory.systemTemp.createTempSync('attach_parts_');
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/path_provider'),
        (call) async => dir.path,
      );
    });

    tearDown(() {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/path_provider'),
        null,
      );
      try {
        dir.deleteSync(recursive: true);
      } catch (_) {}
    });

    testWidgets('three files show one button; hover lights them; merge sends all',
        (tester) async {
      final attached = <Object?>[];
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
            jsonEncode({
              'ok': true,
              'papers': [
                {
                  'id': 'c1',
                  'title': _title,
                  'sentence_count': 3,
                  'source_name': 's41467-021-24079-8.pdf',
                },
                {
                  'id': 'c2',
                  'title': 'Supporting Information $_title',
                  'doc_role': 'supplementary',
                  'sentence_count': 2,
                  'source_name': '41467_2021_24079_MOESM1_ESM.pdf',
                },
                {
                  'id': 'c3',
                  'title': 'REVIEWER COMMENTS',
                  'doc_kind': 'review',
                  'sentence_count': 4,
                  'source_name': '41467_2021_24079_MOESM2_ESM.pdf',
                },
              ],
            }),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          );
        }
        if (path.endsWith('/attach')) {
          attached.add(jsonDecode(request.body));
          return http.Response('{"ok":true,"cache_id":"c1"}', 200);
        }
        return http.Response('{}', 404);
      });
      final store = MemorySessionStore();
      await store.writeToken('tok');
      final client = AsrClient(httpClient: mock, sessionStore: store);
      final auth = AuthController(client: client);
      final lib = LibraryController(
        client: client,
        draftStore: MemoryUploadDraftStore(),
      );
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

      expect([for (final e in lib.papers) e.id], ['c1', 'c3']);
      final button = find.byKey(const ValueKey('library_merge_c1'));
      expect(button, findsOneWidget);
      expect(find.text('3개 합치기'), findsOneWidget);

      final mouse = await tester.createGesture(kind: PointerDeviceKind.mouse);
      await mouse.addPointer(location: Offset.zero);
      addTearDown(mouse.removePointer);
      await mouse.moveTo(tester.getCenter(button));
      await tester.pump();
      expect(find.byKey(const ValueKey('merge_lit_c1')), findsOneWidget);
      expect(find.byKey(const ValueKey('merge_lit_c3')), findsOneWidget);
      await mouse.moveTo(Offset.zero);
      await tester.pump();
      expect(find.byKey(const ValueKey('merge_lit_c3')), findsNothing);

      await tester.tap(button);
      await tester.pumpAndSettle();
      expect(find.textContaining('심사 기록 — REVIEWER COMMENTS'), findsOneWidget);
      await tester.runAsync(() async {
        await tester.tap(find.byKey(const ValueKey('attach_confirm')));
        await Future<void>.delayed(const Duration(milliseconds: 500));
      });
      await tester.pump();
      expect(attached, [
        {
          'parts': [
            {'id': 'c2', 'section': 'supplementary'},
            {'id': 'c3', 'section': 'review'},
          ],
        },
      ]);
    });
  });
}
