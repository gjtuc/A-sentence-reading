import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/services/tts_audio_cache.dart';

void main() {
  test('same sentence, voice, rate and rules share one name', () {
    final a = ttsAudioKey(
      text: 'Fuel cell',
      voice: 'en-US-Neural2-D',
      rate: 1.0,
      speakNorm: 'v6',
    );
    final same = ttsAudioKey(
      text: '  Fuel cell  ',
      voice: 'en-US-Neural2-D',
      rate: 1.0,
      speakNorm: 'v6',
    );
    expect(a, same);

    for (final other in [
      ttsAudioKey(
        text: 'Fuel cells',
        voice: 'en-US-Neural2-D',
        rate: 1.0,
        speakNorm: 'v6',
      ),
      ttsAudioKey(
        text: 'Fuel cell',
        voice: 'en-US-Neural2-A',
        rate: 1.0,
        speakNorm: 'v6',
      ),
      ttsAudioKey(
        text: 'Fuel cell',
        voice: 'en-US-Neural2-D',
        rate: 0.9,
        speakNorm: 'v6',
      ),
      ttsAudioKey(
        text: 'Fuel cell',
        voice: 'en-US-Neural2-D',
        rate: 1.0,
        speakNorm: 'v7',
      ),
    ]) {
      expect(other, isNot(a));
    }
  });

  test('a folder under the cap keeps every file', () {
    final keep = ttsCacheEvictions(
      files: [
        (path: 'a', bytes: 10, stampMs: 1),
        (path: 'b', bytes: 20, stampMs: 2),
      ],
      maxBytes: 100,
    );
    expect(keep, isEmpty);
  });

  test('the oldest files go first until the folder fits', () {
    final drop = ttsCacheEvictions(
      files: [
        (path: 'new', bytes: 40, stampMs: 300),
        (path: 'old', bytes: 40, stampMs: 100),
        (path: 'mid', bytes: 40, stampMs: 200),
      ],
      maxBytes: 60,
    );
    expect(drop, ['old', 'mid']);
  });
}
