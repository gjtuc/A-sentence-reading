import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/app.dart';

void main() {
  testWidgets('home shell shows brand title', (tester) async {
    await tester.pumpWidget(const SentenceReadingApp());
    expect(find.textContaining('문장 읽기'), findsWidgets);
  });
}
