import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/services/hang_watchdog.dart';

void main() {
  test('0.3.123 same percent + different stage text resets stall', () async {
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

    hang.begin(
      'job1',
      stage: 'translate',
      stallAfter: const Duration(milliseconds: 200),
    );
    await Future<void>.delayed(const Duration(milliseconds: 80));
    hang.progress('job1', stage: 'translate'); // msg-equivalent progress
    await Future<void>.delayed(const Duration(milliseconds: 80));
    expect(fired, isEmpty);
    await Future<void>.delayed(const Duration(milliseconds: 200));
    expect(fired, contains('local:hang'));
    hang.dispose();
  });

  test('setStallAfter lengthens window', () async {
    final fired = <String>[];
    final hang = HangWatchdog(
      onLocal: (opId, kind) {
        fired.add(kind);
      },
    );
    hang.begin(
      'job2',
      stage: 'translate',
      stallAfter: const Duration(milliseconds: 100),
    );
    hang.setStallAfter('job2', const Duration(milliseconds: 400));
    await Future<void>.delayed(const Duration(milliseconds: 200));
    expect(fired, isEmpty);
    await Future<void>.delayed(const Duration(milliseconds: 250));
    expect(fired, contains('hang'));
    hang.dispose();
  });
}
