/// design/212 — local accuracy samples + day aggregates (no transcripts).
library;

import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../api/focus_practice_models.dart';

const String kSkillPrefsKeyBase = 'asr.practice_skill.v1';

String skillPrefsKey(String? uid) {
  final u = (uid ?? '').trim();
  if (u.isEmpty) return kSkillPrefsKeyBase;
  return '$kSkillPrefsKeyBase.$u';
}

class SkillDayAgg {
  const SkillDayAgg({this.sum = 0, this.n = 0});
  final double sum;
  final int n;
  double? get mean => n <= 0 ? null : sum / n;
  SkillDayAgg add(double accuracy) =>
      SkillDayAgg(sum: sum + accuracy, n: n + 1);
}

class SkillState {
  const SkillState({
    this.version = 1,
    this.tier = 2,
    this.density = 0,
    this.days = const {},
    this.blockSum = 0,
    this.blockN = 0,
    this.cooldownBlocks = 0,
  });

  final int version;
  final int tier; // 0..5
  final int density; // -2..2
  final Map<String, SkillDayAgg> days;
  final double blockSum;
  final int blockN;
  final int cooldownBlocks;

  SkillState copyWith({
    int? tier,
    int? density,
    Map<String, SkillDayAgg>? days,
    double? blockSum,
    int? blockN,
    int? cooldownBlocks,
  }) {
    return SkillState(
      version: version,
      tier: tier ?? this.tier,
      density: density ?? this.density,
      days: days ?? this.days,
      blockSum: blockSum ?? this.blockSum,
      blockN: blockN ?? this.blockN,
      cooldownBlocks: cooldownBlocks ?? this.cooldownBlocks,
    );
  }

  Map<String, dynamic> toJson() => {
        'version': version,
        'tier': tier,
        'density': density,
        'block_sum': blockSum,
        'block_n': blockN,
        'cooldown_blocks': cooldownBlocks,
        'days': {
          for (final e in days.entries)
            e.key: {'sum': e.value.sum, 'n': e.value.n},
        },
      };

  static SkillState fromJson(Map<String, dynamic> m) {
    final days = <String, SkillDayAgg>{};
    final raw = m['days'];
    if (raw is Map) {
      for (final e in raw.entries) {
        final v = e.value;
        if (v is Map) {
          days['${e.key}'] = SkillDayAgg(
            sum: (v['sum'] as num?)?.toDouble() ?? 0,
            n: (v['n'] as num?)?.toInt() ?? 0,
          );
        }
      }
    }
    return SkillState(
      version: (m['version'] as num?)?.toInt() ?? 1,
      tier: ((m['tier'] as num?)?.toInt() ?? 2).clamp(0, 5),
      density: ((m['density'] as num?)?.toInt() ?? 0).clamp(-2, 2),
      days: days,
      blockSum: (m['block_sum'] as num?)?.toDouble() ?? 0,
      blockN: (m['block_n'] as num?)?.toInt() ?? 0,
      cooldownBlocks: (m['cooldown_blocks'] as num?)?.toInt() ?? 0,
    );
  }
}

class SkillStore {
  String? _uid;
  SkillState state = const SkillState();

  Future<void> bindUid(String? uid) async {
    _uid = uid;
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(skillPrefsKey(_uid));
    if (raw == null || raw.isEmpty) {
      state = const SkillState();
      return;
    }
    try {
      final m = jsonDecode(raw);
      if (m is Map<String, dynamic>) {
        state = SkillState.fromJson(m);
      } else if (m is Map) {
        state = SkillState.fromJson(Map<String, dynamic>.from(m));
      }
    } catch (_) {
      state = const SkillState();
    }
  }

  Future<void> _persist() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(skillPrefsKey(_uid), jsonEncode(state.toJson()));
  }

  Future<void> addScored(double accuracy, {String? dayKey}) async {
    final day = dayKey ?? focusPracticeDayKey();
    final days = Map<String, SkillDayAgg>.from(state.days);
    days[day] = (days[day] ?? const SkillDayAgg()).add(accuracy);
    state = state.copyWith(
      days: days,
      blockSum: state.blockSum + accuracy,
      blockN: state.blockN + 1,
    );
    await _persist();
  }

  Future<void> setTierDensity({int? tier, int? density, int? cooldown}) async {
    state = state.copyWith(
      tier: tier,
      density: density,
      cooldownBlocks: cooldown,
    );
    await _persist();
  }

  Future<void> resetBlockAccum() async {
    state = state.copyWith(blockSum: 0, blockN: 0);
    await _persist();
  }

  Future<void> onBlockBoundary() async {
    var cd = state.cooldownBlocks;
    if (cd > 0) cd -= 1;
    state = state.copyWith(blockSum: 0, blockN: 0, cooldownBlocks: cd);
    await _persist();
  }

  double? dayMean(String dayKey) => state.days[dayKey]?.mean;

  int dayN(String dayKey) => state.days[dayKey]?.n ?? 0;
}
