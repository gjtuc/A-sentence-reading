import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/practice_rhythm/follow_span.dart';
import 'package:sentence_reading/practice_skill/spoken_disk_cache.dart';

void main() {
  test('a saved row keeps each word phone', () {
    const spans = [
      FollowSpan(start: 0, end: 4, weight: 4, phone: 'f j uː l'),
      FollowSpan(start: 5, end: 9, weight: 4, phone: 's ɛ l'),
    ];
    final row = decodeSpokenRow(encodeSpokenRow('Fuel cell', spans));
    expect(row, isNotNull);
    expect(row!.spoken, 'Fuel cell');
    expect(row.spans, hasLength(2));
    expect(row.spans.first.phone, 'f j uː l');
    expect(row.spans.last.weight, 4);
  });

  test('a row without spoken text is dropped', () {
    expect(decodeSpokenRow({'s': '  ', 'p': []}), isNull);
    expect(decodeSpokenRow('nope'), isNull);
  });

  test('the store keeps the newest rows', () {
    final rows = <String, Object?>{};
    for (var i = 0; i < kSpokenDiskMaxRows + 5; i++) {
      rows['k$i'] = encodeSpokenRow('row $i', const []);
    }
    final trimmed = trimSpokenRows(rows);
    expect(trimmed, hasLength(kSpokenDiskMaxRows));
    expect(trimmed.containsKey('k0'), isFalse);
    expect(trimmed.containsKey('k${kSpokenDiskMaxRows + 4}'), isTrue);
  });
}
