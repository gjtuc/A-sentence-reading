import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/tts_models.dart';

void main() {
  group('clampSpeakingRate', () {
    test('normal', () {
      expect(clampSpeakingRate(1.0), 1.0);
      expect(clampSpeakingRate(1.25), 1.25);
    });
    test('edges', () {
      expect(clampSpeakingRate(null), kTtsRateDefault);
      expect(clampSpeakingRate(0), kTtsRateMin);
      expect(clampSpeakingRate(-9), kTtsRateMin);
      expect(clampSpeakingRate(99), kTtsRateMax);
      expect(clampSpeakingRate(double.nan), kTtsRateDefault);
      expect(clampSpeakingRate(double.infinity), kTtsRateDefault);
    });
  });

  group('isEmptyTtsText', () {
    test('edges', () {
      expect(isEmptyTtsText(null), isTrue);
      expect(isEmptyTtsText(''), isTrue);
      expect(isEmptyTtsText('   \n\t'), isTrue);
      expect(isEmptyTtsText('Ni'), isFalse);
    });
  });

  group('TtsVoicesInfo.fromJson', () {
    test('null and partial', () {
      final a = TtsVoicesInfo.fromJson(null);
      expect(a.available, isFalse);
      expect(a.defaultVoice, kTtsDefaultVoice);
      final b = TtsVoicesInfo.fromJson({
        'available': true,
        'voices': [
          'en-US-Neural2-D',
          {'name': 'en-GB-Neural2-A'},
          123,
          '',
        ],
        'rate_min': -1,
        'rate_max': 50,
      });
      expect(b.available, isTrue);
      expect(b.voices, ['en-US-Neural2-D', 'en-GB-Neural2-A']);
      expect(b.rateMin, kTtsRateMin);
      expect(b.rateMax, kTtsRateMax);
    });
  });
}
