import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/launch_dest.dart';

void main() {
  test('launch dest ignores missing and deleted papers', () {
    const live = {'a', 'b'};
    final at = {'a': '2026-01-01T00:00:00Z', 'gone': '2026-09-01T00:00:00Z'};
    expect(latestLiveCacheId(at, live), 'a');
    expect(latestLiveCacheId({'gone': '2026-09-01'}, live), isNull);
  });

  test('practice launch needs shadowing and the latest live practice paper', () {
    final at = {
      'old': '2026-01-01T00:00:00Z',
      'new': '2026-06-01T00:00:00Z',
    };
    final off = resolveLaunchOpen(
      dest: LaunchDest.practice,
      shadowingOn: false,
      readAt: at,
      practiceAt: at,
      liveIds: {'old', 'new'},
    );
    expect(off, isNull);
    final on = resolveLaunchOpen(
      dest: LaunchDest.practice,
      shadowingOn: true,
      readAt: at,
      practiceAt: at,
      liveIds: {'old', 'new'},
    );
    expect(on?.cacheId, 'new');
    expect(on?.practice, isTrue);
  });

  test('read launch uses reading recency and library stays put', () {
    final stay = resolveLaunchOpen(
      dest: LaunchDest.library,
      shadowingOn: true,
      readAt: {'a': '2026-01-01T00:00:00Z'},
      practiceAt: {'a': '2026-08-01T00:00:00Z'},
      liveIds: {'a'},
    );
    expect(stay, isNull);
    final read = resolveLaunchOpen(
      dest: LaunchDest.read,
      shadowingOn: false,
      readAt: {'a': '2026-02-01T00:00:00Z', 'b': '2026-03-01T00:00:00Z'},
      practiceAt: {'a': '2026-09-01T00:00:00Z'},
      liveIds: {'a', 'b'},
    );
    expect(read?.cacheId, 'b');
    expect(read?.practice, isFalse);
  });

  test('corrupt progress store does not invent a paper', () {
    expect(atByCacheIdFromStore(null), isEmpty);
    expect(
      atByCacheIdFromStore({
        'cache:ok': {'at': '2026-01-01T00:00:00Z', 'sentence_index': 1},
        'other': {'at': '2026-09-01T00:00:00Z'},
        'cache:empty': {'sentence_index': 0},
      }),
      {'ok': '2026-01-01T00:00:00Z'},
    );
  });
}
