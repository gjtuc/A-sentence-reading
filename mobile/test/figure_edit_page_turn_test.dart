// design/438 - the figure layout editor turns pages by swipe and by ←/→.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:sentence_reading/api/client.dart';
import 'package:sentence_reading/api/session_store.dart';
import 'package:sentence_reading/screens/figure_edit_screen.dart';

const _page = '{"width_pt":612,"height_pt":792}';

AsrClient _client() {
  final mock = MockClient((request) async {
    final path = request.url.path;
    if (path.endsWith('/layout_map')) {
      return http.Response(
        '{"ok":true,"layout_map":{"pages":[$_page,$_page,$_page],"boxes":[]}}',
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (path.endsWith('/slot_plan')) {
      return http.Response(
        '{"ok":true,"slot_plan":{"slots":[]}}',
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    return http.Response('{}', 404);
  });
  return AsrClient(httpClient: mock, sessionStore: MemorySessionStore());
}

Future<void> _pumpEditor(WidgetTester tester) async {
  tester.view.physicalSize = const Size(411, 891);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: FigureEditScreen(client: _client(), cacheId: 'c1'),
  ));
  for (var i = 0; i < 5; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

void main() {
  testWidgets('the bar shows the page out of all pages, with no page arrows',
      (tester) async {
    await _pumpEditor(tester);
    expect(find.text('1 / 3쪽'), findsOneWidget);
    expect(find.text('p.1'), findsNothing);
    expect(find.byTooltip('next page'), findsNothing);
    expect(find.byTooltip('prev page'), findsNothing);
  });

  testWidgets('←/→ turn the page and stop at the first and last page',
      (tester) async {
    await _pumpEditor(tester);
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pump();
    expect(find.text('2 / 3쪽'), findsOneWidget);
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
    await tester.pump();
    expect(find.text('1 / 3쪽'), findsOneWidget);
    for (var i = 0; i < 4; i++) {
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    }
    await tester.pump();
    expect(find.text('3 / 3쪽'), findsOneWidget);
  });

  testWidgets('a swipe turns the page in the default Select mode',
      (tester) async {
    await _pumpEditor(tester);
    await tester.fling(
      find.byType(InteractiveViewer),
      const Offset(-300, 0),
      1500,
    );
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('2 / 3쪽'), findsOneWidget);
    await tester.fling(
      find.byType(InteractiveViewer),
      const Offset(300, 0),
      1500,
    );
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('1 / 3쪽'), findsOneWidget);
  });
}
