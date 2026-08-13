import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/services/hang_watchdog.dart';

void main() {
  test('design/134 progress resets stall; same stage alone does not evade', () async {
    final fired = <String>[];
    final hang = HangWatchdog(
      onHang: ({
        required String kind,
        required String message,
        String stage = '',
        String? paperTitle,
        String? cacheId,
      }) async {
        fired.add(kind);
      },
      onLocal: (opId, kind) {
        fired.add('local:$kind');
      },
    );

    hang.begin('op1', stage: 'uploading', stallAfter: const Duration(milliseconds: 200));
    await Future<void>.delayed(const Duration(milliseconds: 80));
    hang.progress('op1', stage: 'processing'); // real forward
    await Future<void>.delayed(const Duration(milliseconds: 80));
    expect(fired, isEmpty);
    await Future<void>.delayed(const Duration(milliseconds: 200));
    expect(fired, contains('local:hang'));
    expect(fired, contains('hang'));
    hang.dispose();
  });
}
