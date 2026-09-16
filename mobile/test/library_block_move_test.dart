import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/state/library_block_move.dart';
import 'package:sentence_reading/widgets/library_card_hold.dart';

void main() {
  test('design/308 move checked rows as one block', () {
    expect(
      moveIdsAsBlock(['A', 'B', 'C', 'D', 'E'], ['B', 'D'], 2),
      ['A', 'B', 'D', 'C', 'E'],
    );
    expect(
      moveIdsAsBlock(['A', 'B', 'C', 'D', 'E'], ['B', 'D'], 0),
      ['B', 'D', 'A', 'C', 'E'],
    );
    expect(
      moveIdsAsBlock(['A', 'B', 'C', 'D', 'E'], ['B', 'D'], 5),
      ['A', 'C', 'E', 'B', 'D'],
    );
    expect(moveIdsAsBlock(['A', 'B', 'C'], ['B'], 1), ['A', 'B', 'C']);
    expect(moveIdsAsBlock(['A', 'B', 'C'], const <String>[], 1), ['A', 'B', 'C']);
    expect(moveIdsAsBlock(['A', 'B'], ['Z'], 0), ['A', 'B']);
  });

  testWidgets('design/308 hold drag survives parent rebuild', (tester) async {
    var starts = 0;
    var ends = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: StatefulBuilder(
          builder: (context, setLocal) {
            return LibraryCardHold(
              enabled: true,
              onHold: (_) {},
              onDragStart: (_) {
                starts += 1;
                setLocal(() {});
              },
              onDragUpdate: (_) {},
              onDragEnd: (_) => ends += 1,
              onCancel: () {},
              child: const SizedBox(width: 200, height: 80, child: Text('row')),
            );
          },
        ),
      ),
    );
    final gesture = await tester.startGesture(tester.getCenter(find.text('row')));
    await tester.pump(const Duration(milliseconds: 520));
    await gesture.moveBy(const Offset(0, 30));
    await tester.pump();
    await gesture.moveBy(const Offset(0, 40));
    await gesture.up();
    await tester.pump();
    expect(starts, 1);
    expect(ends, 1);
  });
}
