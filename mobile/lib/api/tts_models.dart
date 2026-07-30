/// Pure helpers for Flutter TTS (design/64).
///
/// WHY separate from audioplayers: unit tests can clamp / refuse empty text
/// without a device audio plugin.
library;

/// Server voices advertise 0.5–2.2; clamp before setPlaybackRate.
const double kTtsRateMin = 0.5;
const double kTtsRateMax = 2.2;
const double kTtsRateDefault = 1.0;

/// Default curated Neural2 voice (matches `/api/tts/voices` default).
const String kTtsDefaultVoice = 'en-US-Neural2-D';

/// Clamp speaking / playback rate into the API-advertised band.
///
/// EDGE: NaN / Infinity / null-like → default 1.0.
double clampSpeakingRate(num? raw) {
  if (raw == null) return kTtsRateDefault;
  final v = raw.toDouble();
  if (v.isNaN || v.isInfinite) return kTtsRateDefault;
  if (v < kTtsRateMin) return kTtsRateMin;
  if (v > kTtsRateMax) return kTtsRateMax;
  return v;
}

/// True when [text] has nothing Cloud TTS should synthesize.
bool isEmptyTtsText(String? text) {
  if (text == null) return true;
  return text.trim().isEmpty;
}

/// Voices payload subset from GET /api/tts/voices.
class TtsVoicesInfo {
  TtsVoicesInfo({
    required this.available,
    required this.defaultVoice,
    required this.rateMin,
    required this.rateMax,
    this.voices = const [],
  });

  factory TtsVoicesInfo.fromJson(Map<String, dynamic>? json) {
    if (json == null) {
      return TtsVoicesInfo(
        available: false,
        defaultVoice: kTtsDefaultVoice,
        rateMin: kTtsRateMin,
        rateMax: kTtsRateMax,
      );
    }
    final voicesRaw = json['voices'];
    final voices = <String>[];
    if (voicesRaw is List) {
      for (final item in voicesRaw) {
        if (item is String && item.trim().isNotEmpty) {
          voices.add(item.trim());
        } else if (item is Map && item['name'] != null) {
          final name = '${item['name']}'.trim();
          if (name.isNotEmpty) voices.add(name);
        }
      }
    }
    final minR = json['rate_min'] is num ? json['rate_min'] as num : kTtsRateMin;
    final maxR = json['rate_max'] is num ? json['rate_max'] as num : kTtsRateMax;
    final min = clampSpeakingRate(minR);
    final max = clampSpeakingRate(maxR);
    final dVoice = '${json['default_voice'] ?? kTtsDefaultVoice}'.trim();
    return TtsVoicesInfo(
      available: json['available'] == true,
      defaultVoice: dVoice.isEmpty ? kTtsDefaultVoice : dVoice,
      rateMin: min <= max ? min : kTtsRateMin,
      rateMax: max >= min ? max : kTtsRateMax,
      voices: voices,
    );
  }

  final bool available;
  final String defaultVoice;
  final double rateMin;
  final double rateMax;
  final List<String> voices;
}
