/// Pure helpers for Flutter TTS (design/64 · design/103).
///
/// WHY separate from audioplayers: unit tests can clamp / refuse empty text
/// and pick random playback params without a device audio plugin.
library;

import 'dart:math';

/// Server voices advertise 0.5–2.2; clamp before setPlaybackRate.
const double kTtsRateMin = 0.5;
const double kTtsRateMax = 2.2;
const double kTtsRateDefault = 1.0;

/// Default curated Neural2 voice (matches `/api/tts/voices` default).
const String kTtsDefaultVoice = 'en-US-Neural2-D';

const String kTtsModeFixed = 'fixed';
const String kTtsModeRandomNormal = 'random_normal';
const String kTtsModeRandomHard = 'random_hard';
const String kTtsModeRandomVeryHard = 'random_very_hard';
const String kTtsModeRandomAuto = 'random_auto';

/// Prefs keys (design/96 · design/103).
const String kTtsRatePrefsKey = 'asr_tts_rate_v1';
const String kTtsModePrefsKey = 'asr_tts_mode_v1';
const String kTtsVoicePrefsKey = 'asr_tts_voice_v1';

/// Modes understood by playback helpers (includes legacy bands).
const Set<String> kTtsModes = {
  kTtsModeFixed,
  kTtsModeRandomAuto,
  kTtsModeRandomNormal,
  kTtsModeRandomHard,
  kTtsModeRandomVeryHard,
};

/// design/224 — Settings UI modes only (migrate legacy → random_auto first).
const Set<String> kTtsModesUi = {
  kTtsModeFixed,
  kTtsModeRandomAuto,
};

/// Ordered Settings dropdown values (design/224).
const List<String> kTtsModesUiOrdered = [
  kTtsModeFixed,
  kTtsModeRandomAuto,
];

const Set<String> kTtsRandomModes = {
  kTtsModeRandomAuto,
  kTtsModeRandomNormal,
  kTtsModeRandomHard,
  kTtsModeRandomVeryHard,
};

/// design/212 — six skill tiers (rate/locale bands). Default tier 2 = normal.
const Map<int, (double, double)> kTtsSkillTier = {
  0: (0.55, 0.85),
  1: (0.65, 1.00),
  2: (0.70, 1.30),
  3: (0.90, 1.45),
  4: (1.00, 1.60),
  5: (1.30, 1.90),
};

const Map<int, Map<String, double>> kTtsSkillLocaleWeights = {
  0: {'en-US': 1.0},
  1: {'en-US': 0.9, 'en-GB': 0.1},
  2: {'en-US': 0.8, 'en-GB': 0.2},
  3: {'en-US': 0.5, 'en-GB': 0.3, 'en-AU': 0.2},
  4: {'en-US': 0.4, 'en-GB': 0.3, 'en-AU': 0.3},
  5: {
    'en-US': 0.2,
    'en-GB': 0.2,
    'en-AU': 0.25,
    'en-IN': 0.35,
  },
};

const Map<String, int> kTtsLegacyModeToTier = {
  kTtsModeRandomNormal: 2,
  kTtsModeRandomHard: 4,
  kTtsModeRandomVeryHard: 5,
};

/// Random mode rate bands (web `TTS_RATE_BANDS`).
const Map<String, (double, double)> kTtsRateBands = {
  kTtsModeRandomAuto: (0.7, 1.3),
  kTtsModeRandomNormal: (0.7, 1.3),
  kTtsModeRandomHard: (1.0, 1.6),
  kTtsModeRandomVeryHard: (1.3, 1.9),
};

/// Locale weights per random mode (web `TTS_LOCALE_WEIGHTS`).
const Map<String, Map<String, double>> kTtsLocaleWeights = {
  kTtsModeRandomAuto: {'en-US': 0.8, 'en-GB': 0.2},
  kTtsModeRandomNormal: {'en-US': 0.8, 'en-GB': 0.2},
  kTtsModeRandomHard: {'en-US': 0.4, 'en-GB': 0.3, 'en-AU': 0.3},
  kTtsModeRandomVeryHard: {
    'en-US': 0.2,
    'en-GB': 0.2,
    'en-AU': 0.25,
    'en-IN': 0.35,
  },
};

/// Korean labels for Settings dropdown (design/224 · legacy labels kept for tests).
String ttsModeLabelKo(String mode) {
  switch (normalizeTtsModeUi(mode)) {
    case kTtsModeRandomAuto:
      return '랜덤';
    case kTtsModeFixed:
    default:
      return '사용자 선택';
  }
}


String ttsSkillTierLabelKo(int tier) {
  switch (tier.clamp(0, 5)) {
    case 0:
      return '쉬움';
    case 1:
      return '약간 쉬움';
    case 2:
      return '보통';
    case 3:
      return '약간 어려움';
    case 4:
      return '어려움';
    case 5:
      return '많이 어려움';
    default:
      return '보통';
  }
}

({String mode, int tier}) migrateTtsModeAndTier(String? mode, {int? tier}) {
  final m = (mode ?? '').trim();
  if (m == kTtsModeRandomAuto) {
    return (mode: kTtsModeRandomAuto, tier: (tier ?? 2).clamp(0, 5));
  }
  if (kTtsLegacyModeToTier.containsKey(m)) {
    return (mode: kTtsModeRandomAuto, tier: kTtsLegacyModeToTier[m]!);
  }
  if (m == kTtsModeFixed || m.isEmpty) {
    return (mode: kTtsModeFixed, tier: (tier ?? 2).clamp(0, 5));
  }
  return (mode: kTtsModeFixed, tier: 2);
}

String ttsModeHintKo(String mode) {
  if (isTtsRandomMode(mode)) {
    return '재생마다 목소리와 속도가 바뀝니다.';
  }
  return '아래에서 고른 목소리와 속도로 고정 재생합니다.';
}

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

bool isTtsRandomMode(String? mode) =>
    kTtsRandomModes.contains(normalizeTtsMode(mode));

String normalizeTtsMode(String? raw) {
  final m = (raw ?? '').trim();
  if (kTtsModes.contains(m)) return m;
  return kTtsModeFixed;
}

/// design/224 — UI/prefs surface after migrateTtsModeAndTier.
String normalizeTtsModeUi(String? raw) {
  final migrated = migrateTtsModeAndTier(raw);
  if (kTtsModesUi.contains(migrated.mode)) return migrated.mode;
  return kTtsModeFixed;
}

String normalizeTtsVoice(String? raw, {String fallback = kTtsDefaultVoice}) {
  final v = (raw ?? '').trim();
  if (v.isEmpty || v == 'undefined' || v == 'null' || v == 'None') {
    return fallback;
  }
  return v;
}

/// One curated voice from GET /api/tts/voices (`{id, label}`).
class TtsVoiceChoice {
  const TtsVoiceChoice({required this.id, required this.label});

  final String id;
  final String label;
}

/// Result of fixed/random pick for one play.
class TtsPlaybackParams {
  const TtsPlaybackParams({
    required this.voice,
    required this.speakingRate,
    required this.mode,
  });

  final String voice;
  final double speakingRate;
  final String mode;
}

List<String> listTtsVoiceIdsForLocale(List<String> voiceIds, String locale) {
  final prefix = '${locale.isEmpty ? 'en-US' : locale}-';
  final matched =
      voiceIds.where((id) => id.startsWith(prefix)).toList(growable: false);
  if (matched.isNotEmpty) return matched;
  if (locale != 'en-US') {
    return listTtsVoiceIdsForLocale(voiceIds, 'en-US');
  }
  return voiceIds.isNotEmpty
      ? voiceIds
      : const [kTtsDefaultVoice];
}

String pickWeightedLocale(String mode, Random random) {
  final weights = kTtsLocaleWeights[normalizeTtsMode(mode)];
  if (weights == null || weights.isEmpty) return 'en-US';
  final entries =
      weights.entries.where((e) => e.value > 0).toList(growable: false);
  if (entries.isEmpty) return 'en-US';
  var r = random.nextDouble();
  var acc = 0.0;
  for (final e in entries) {
    acc += e.value;
    if (r <= acc) return e.key;
  }
  return entries.last.key;
}

/// Pick voice + client playback rate (server always synthesizes at 1.0).
TtsPlaybackParams pickTtsPlaybackParams({
  required String mode,
  required String voice,
  required double speakingRate,
  List<String> voiceIds = const [],
  Random? random,
  int? skillTier,
}) {
  final m = normalizeTtsMode(mode);
  if (isTtsRandomMode(m)) {
    final rng = random ?? Random();
    late final (double, double) band;
    Map<String, double>? weights;
    if (m == kTtsModeRandomAuto) {
      final ti = (skillTier ?? 2).clamp(0, 5);
      band = kTtsSkillTier[ti] ?? (0.7, 1.3);
      weights = kTtsSkillLocaleWeights[ti];
    } else {
      band = kTtsRateBands[m] ?? (0.7, 1.3);
      weights = kTtsLocaleWeights[m];
    }
    late String locale;
    if (weights == null || weights.isEmpty) {
      locale = pickWeightedLocale(
        m == kTtsModeRandomAuto ? kTtsModeRandomNormal : m,
        rng,
      );
    } else {
      final entries =
          weights.entries.where((e) => e.value > 0).toList(growable: false);
      var r = rng.nextDouble();
      var acc = 0.0;
      locale = entries.last.key;
      for (final e in entries) {
        acc += e.value;
        if (r <= acc) {
          locale = e.key;
          break;
        }
      }
    }
    final ids = voiceIds.isEmpty
        ? const [kTtsDefaultVoice]
        : voiceIds;
    final pool = listTtsVoiceIdsForLocale(ids, locale);
    final picked = pool[rng.nextInt(pool.length)];
    final rateRaw = band.$1 + rng.nextDouble() * (band.$2 - band.$1);
    final rate = (rateRaw * 100).round() / 100.0;
    return TtsPlaybackParams(
      voice: picked,
      speakingRate: clampSpeakingRate(rate),
      mode: m,
    );
  }
  return TtsPlaybackParams(
    voice: normalizeTtsVoice(voice),
    speakingRate: clampSpeakingRate(speakingRate),
    mode: kTtsModeFixed,
  );
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
    final voices = <TtsVoiceChoice>[];
    if (voicesRaw is List) {
      for (final item in voicesRaw) {
        if (item is String && item.trim().isNotEmpty) {
          final id = item.trim();
          voices.add(TtsVoiceChoice(id: id, label: id));
        } else if (item is Map) {
          final id = '${item['id'] ?? item['name'] ?? ''}'.trim();
          if (id.isEmpty || id == 'undefined' || id == 'null') continue;
          final label = '${item['label'] ?? id}'.trim();
          voices.add(TtsVoiceChoice(
            id: id,
            label: label.isEmpty ? id : label,
          ));
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
  final List<TtsVoiceChoice> voices;

  List<String> get voiceIds =>
      voices.map((v) => v.id).toList(growable: false);
}
