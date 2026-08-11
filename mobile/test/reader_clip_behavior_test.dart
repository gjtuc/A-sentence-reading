/// design/115 — Container clipBehavior without decoration must not ship.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('clipBehavior on Container without decoration throws',
      (tester) async {
    // WHY: documents Flutter contract that blanked the reader (title-only).
    // EDGE: release builds strip assert() but still hit decoration!.
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AnimatedContainer(
            duration: Duration.zero,
            height: 80,
            clipBehavior: Clip.hardEdge,
            child: const Text('panel'),
          ),
        ),
      ),
    );
    final err = tester.takeException();
    // Debug: assert at container.dart ~275; release: TypeError on decoration!.
    expect(err, isNotNull);
  });

  testWidgets('ClipRect + AnimatedContainer without clipBehavior paints',
      (tester) async {
    // WHY: design/115 fix path used by reader_screen sentence/figure panes.
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ClipRect(
            child: AnimatedContainer(
              duration: Duration.zero,
              height: 80,
              child: const Text('panel-ok'),
            ),
          ),
        ),
      ),
    );
    expect(tester.takeException(), isNull);
    expect(find.text('panel-ok'), findsOneWidget);
  });
}
