// design/383 — a paper opened from this phone's own disk never reaches /open,
// so the server is never told to build its reference sounds. The phone has to
// say so itself, and saying so must never be able to break opening the paper.
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sentence_reading/api/client.dart';
import 'package:sentence_reading/api/session_store.dart';

void main() {
  test('design/383 askSoundWarm posts to the paper and reports the code',
      () async {
    final store = MemorySessionStore();
    await store.writeToken('tok');
    final seen = <String>[];
    final client = AsrClient(
      httpClient: MockClient((request) async {
        seen.add('${request.method} ${request.url.path}');
        return http.Response(
          '{"ok":true,"warm":"started"}',
          200,
          headers: {'content-type': 'application/json'},
        );
      }),
      sessionStore: store,
    );

    final code = await client.askSoundWarm(' 7d506b60fb6b ');

    expect(code, 'started');
    expect(seen.single, 'POST /api/cache/papers/7d506b60fb6b/sound-warm');
  });

  test('design/383 askSoundWarm carries back the reason a warm was refused',
      () async {
    final store = MemorySessionStore();
    await store.writeToken('tok');
    final client = AsrClient(
      httpClient: MockClient((_) async => http.Response(
            '{"ok":true,"warm":"no_paper"}',
            200,
            headers: {'content-type': 'application/json'},
          )),
      sessionStore: store,
    );

    expect(await client.askSoundWarm('abc'), 'no_paper');
  });

  test('design/383 a warm we could not ask for never throws', () async {
    final store = MemorySessionStore();
    await store.writeToken('tok');
    final client = AsrClient(
      httpClient: MockClient(
        (_) async => throw http.ClientException('no network'),
      ),
      sessionStore: store,
    );

    // Opening the paper is what matters; the warm is the thing that can wait.
    expect(await client.askSoundWarm('abc'), 'ask_failed');
    expect(await client.askSoundWarm('   '), 'bad_cache_id');
  });

  test('design/383 an old server that has no such route is just a code',
      () async {
    final store = MemorySessionStore();
    await store.writeToken('tok');
    final client = AsrClient(
      httpClient: MockClient((_) async => http.Response('{}', 404)),
      sessionStore: store,
    );

    expect(await client.askSoundWarm('abc'), 'http_404');
  });
}
