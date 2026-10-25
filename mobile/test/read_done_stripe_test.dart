// design/452 — a finished paper's row shows a blue bar; the badge is blue too.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/widgets/read_done_badge.dart';

Widget _row(bool on) => MaterialApp(
      home: Scaffold(
        body: Align(
          alignment: Alignment.topLeft,
          child: SizedBox(
          width: 300,
          child: ReadDoneStripe(
            on: on,
            child: Container(
              key: const ValueKey('row'),
              decoration: BoxDecoration(
                border: Border.all(color: Colors.green.shade600, width: 2),
                borderRadius: BorderRadius.circular(8),
              ),
              child: const SizedBox(height: 60, child: Text('paper')),
            ),
          ),
        ),
        ),
      ),
    );

void main() {
  testWidgets('the blue bar runs down the left edge of a read row', (tester) async {
    await tester.pumpWidget(_row(true));
    final bar = find.byKey(const ValueKey('read_done_stripe'));
    expect(bar, findsOneWidget);
    final row = tester.getRect(find.byKey(const ValueKey('row')));
    final rect = tester.getRect(bar);
    expect(rect.left, row.left);
    expect(rect.height, row.height);
    expect(rect.width, 6);
    final box = tester.widget<Container>(
      find.descendant(of: bar, matching: find.byType(Container)),
    );
    expect((box.decoration! as BoxDecoration).color, kReadDoneColor);
  });

  testWidgets('a row not read has no bar and keeps its own border', (tester) async {
    await tester.pumpWidget(_row(false));
    expect(find.byKey(const ValueKey('read_done_stripe')), findsNothing);
    expect(find.byKey(const ValueKey('row')), findsOneWidget);
  });

  testWidgets('the badge says 다 읽음 in the blue, not the green', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: Scaffold(body: ReadDoneBadge())));
    final text = tester.widget<Text>(find.text('다 읽음'));
    expect(text.style!.color, kReadDoneColor);
    expect(text.style!.fontSize, greaterThanOrEqualTo(12));
    expect(kReadDoneColor, isNot(Colors.green.shade600));
  });
}
