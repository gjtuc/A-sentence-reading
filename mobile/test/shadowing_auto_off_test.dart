import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/shadowing_models.dart';

void main() {
  test('shouldAutoOffShadowing after 90d idle', () {
    final old = DateTime.now().toUtc().subtract(const Duration(days: 91));
    final iso = old.toIso8601String();
    expect(
      shouldAutoOffShadowing(
        ShadowingPrefs(enabled: true, lastPracticePressedAt: iso),
      ),
      isTrue,
    );
    expect(
      shouldAutoOffShadowing(
        ShadowingPrefs(enabled: true, enabledSince: iso),
      ),
      isTrue,
    );
    expect(
      shouldAutoOffShadowing(
        const ShadowingPrefs(enabled: false, lastPracticePressedAt: iso),
      ),
      isFalse,
    );
    final recent = DateTime.now()
        .toUtc()
        .subtract(const Duration(days: 1))
        .toIso8601String();
    expect(
      shouldAutoOffShadowing(
        ShadowingPrefs(enabled: true, lastPracticePressedAt: recent),
      ),
      isFalse,
    );
  });

  test('parseShadowingPrefs round-trip JSON', () {
    final raw = serializeShadowingPrefs(
      const ShadowingPrefs(
        enabled: true,
        enabledSince: '2026-01-01T00:00:00.000Z',
        lastPracticePressedAt: '2026-02-01T00:00:00.000Z',
      ),
    );
    final p = parseShadowingPrefs(raw);
    expect(p.enabled, isTrue);
    expect(p.enabledSince, '2026-01-01T00:00:00.000Z');
    expect(p.lastPracticePressedAt, '2026-02-01T00:00:00.000Z');
  });
}
