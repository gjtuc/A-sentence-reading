import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/screens/settings_screen.dart';
import 'package:sentence_reading/state/web_reading_prefs.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    WebReadingPrefs.instance.resetForTests();
  });
  tearDown(() => WebReadingPrefs.instance.resetForTests());

  testWidgets('design/479 the clause switch flips as soon as it is tapped', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(body: ClauseBreakSwitch()),
    ));
    SwitchListTile tile() => tester.widget(find.byKey(const ValueKey('clause_breaks')));
    expect(tile().value, isFalse);
    await tester.tap(find.byKey(const ValueKey('clause_breaks')));
    await tester.pump();
    expect(WebReadingPrefs.instance.clauseBreaks, isTrue);
    expect(tile().value, isTrue);
    await tester.tap(find.byKey(const ValueKey('clause_breaks')));
    await tester.pump();
    expect(tile().value, isFalse);
  });

  testWidgets('design/479 the font choice marks the font as soon as it is picked', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(body: ReadingFontChoice()),
    ));
    ChoiceChip chip(String label) =>
        tester.widget(find.ancestor(of: find.text(label), matching: find.byType(ChoiceChip)));
    expect(chip('Inter').selected, isFalse);
    await tester.tap(find.text('Inter'));
    await tester.pump();
    expect(WebReadingPrefs.instance.font, WebFont.inter);
    expect(chip('Inter').selected, isTrue);
  });
}
