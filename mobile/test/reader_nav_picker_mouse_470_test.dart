import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/reader_nav_labels.dart';
import 'package:sentence_reading/api/reading_models.dart';
import 'package:sentence_reading/widgets/reader_nav_picker.dart';

void main() {
  testWidgets('design/470: a mouse drag spins the sentence wheel', (tester) async {
    final nav = SectionNavIndex.fromSentences([
      for (var i = 0; i < 20; i++)
        SentenceView(id: 's$i', text: 'Sentence $i.', section: 'body'),
    ]);
    int? picked = -1;
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: TextButton(
                onPressed: () async {
                  picked = await showSectionNavPicker(
                    context: context,
                    nav: nav,
                    currentGlobalIndex: 0,
                  );
                },
                child: const Text('open'),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    await tester.drag(
      find.text('1 / 20'),
      const Offset(0, -160),
      kind: PointerDeviceKind.mouse,
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('OK'));
    await tester.pumpAndSettle();
    expect(picked, isNotNull);
    expect(picked, greaterThan(0));
  });
}
