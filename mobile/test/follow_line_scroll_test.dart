// design/394 - the prompt walks by the line being read, and a finger holds it.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show ScrollDirection;
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/practice_rhythm/follow_span.dart';
import 'package:sentence_reading/practice_rhythm/word_phone_text.dart';

void main() {
  testWidgets('design/394 the key goes on the first lit word only', (tester) async {
    final key = GlobalKey();
    const text = 'multi-walled carbon tubes';
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: WordPhoneText(
          text: text,
          spans: const [],
          style: const TextStyle(fontSize: 20),
          // Both hyphen halves of `multi-walled` are lit.
          follow: (start: 0, end: 12),
          litKey: key,
        ),
      ),
    ));

    expect(find.byKey(key), findsOneWidget);
    final lit = find.descendant(of: find.byKey(key), matching: find.text('multi-'));
    expect(lit, findsOneWidget);
  });

  testWidgets('design/394 no key without a lit word', (tester) async {
    final key = GlobalKey();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: WordPhoneText(
          text: 'carbon tubes',
          spans: const [],
          style: const TextStyle(fontSize: 20),
          litKey: key,
        ),
      ),
    ));
    expect(find.byKey(key), findsNothing);
  });

  testWidgets('design/394 a glide is not a finger, a drag is', (tester) async {
    final controller = ScrollController();
    var held = false;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SizedBox(
          height: 200,
          child: NotificationListener<UserScrollNotification>(
            onNotification: (n) {
              if (n.direction != ScrollDirection.idle) held = true;
              return false;
            },
            child: SingleChildScrollView(
              controller: controller,
              child: const SizedBox(height: 2000, width: 300),
            ),
          ),
        ),
      ),
    ));

    unawaited(controller.animateTo(
      400,
      duration: kFollowLineGlide,
      curve: Curves.easeOut,
    ));
    await tester.pumpAndSettle();
    expect(controller.offset, 400);
    expect(held, isFalse);

    await tester.drag(find.byType(SingleChildScrollView), const Offset(0, 120));
    await tester.pumpAndSettle();
    expect(held, isTrue);
  });

  test('design/394 the line sits in the upper third', () {
    expect(kFollowLineAlign, greaterThan(0));
    expect(kFollowLineAlign, lessThan(0.5));
  });
}
