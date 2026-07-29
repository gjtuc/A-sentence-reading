import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/app.dart';

void main() {
  testWidgets('home shell shows brand title', (tester) async {
    await tester.pumpWidget(const SentenceReadingApp());
    // AppBar title includes 「문장 읽기」 before / after status Future settles.
    expect(find.textContaining('문장 읽기'), findsWidgets);
  });
}
