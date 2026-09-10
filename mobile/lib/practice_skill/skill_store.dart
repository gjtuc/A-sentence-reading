/// design/212+215 — local accuracy samples + day aggregates + epoch means.
library;

import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../api/focus_practice_models.dart';
import 'skill_adapt.dart';

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
    this.version = 2,
    this.tier = 2,
    this.density = 0,
    this.days = const {},
    this.blockSum = 0,
    this.blockN = 0,
    this.cooldownBlocks = 0,
    this.epochMeans = const [],
    this.epochTargetN = kSkillEpochMinN,
  });

  final int version;
  final int tier; // 0..5
  final int density; // -2..2
  final Map<String, SkillDayAgg> days;
  final double blockSum;
  final int blockN;
  final int cooldownBlocks;
  /// Completed focus-block means awaiting epoch resolve (design/215).
  final List<double> epochMeans;
  final int epochTargetN;

  SkillState copyWith({
    int? version,
    int? tier,
    int? density,
    Map<String, SkillDayAgg>? days,
    double? blockSum,
    int? blockN,
    int? cooldownBlocks,
    List<double>? epochMeans,
    int? epochTargetN,
  }) {
    return SkillState(
      version: version ?? this.version,
      tier: tier ?? this.tier,
      density: density ?? this.density,
      days: days ?? this.days,
      blockSum: blockSum ?? this.blockSum,
      blockN: blockN ?? this.blockN,
      cooldownBlocks: cooldownBlocks ?? this.cooldownBlocks,
      epochMeans: epochMeans ?? this.epochMeans,
      epochTargetN: epochTargetN ?? this.epochTargetN,
    );
  }

  Map<String, dynamic> toJson() => {
        'version': version,
        'tier': tier,
        'density': density,
        'block_sum': blockSum,
        'block_n': blockN,
        'cooldown_blocks': cooldownBlocks,
        'epoch_means': epochMeans,
        'epoch_target_n': epochTargetN,
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
    final meansRaw = m['epoch_means'];
    final means = <double>[];
    if (meansRaw is List) {
      for (final v in meansRaw) {
        if (v is num) means.add(v.toDouble());
      }
    }
    var target = (m['epoch_target_n'] as num?)?.toInt();
    if (target == null) {
      target = rollSkillEpochTarget();
    }
    target = target.clamp(kSkillEpochMinN, kSkillEpochMaxN);
    return SkillState(
      version: (m['version'] as num?)?.toInt() ?? 2,
      tier: ((m['tier'] as num?)?.toInt() ?? 2).clamp(0, 5),
      density: ((m['density'] as num?)?.toInt() ?? 0).clamp(-2, 2),
      days: days,
      blockSum: (m['block_sum'] as num?)?.toDouble() ?? 0,
      blockN: (m['block_n'] as num?)?.toInt() ?? 0,
      cooldownBlocks: (m['cooldown_blocks'] as num?)?.toInt() ?? 0,
      epochMeans: means,
      epochTargetN: target,
    );
  }
}

class SkillStore {
  String? _uid;
  SkillState state = SkillState(epochTargetN: rollSkillEpochTarget());

  Future<void> bindUid(String? uid) async {
    _uid = uid;
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(skillPrefsKey(_uid));
    if (raw == null || raw.isEmpty) {
      state = SkillState(epochTargetN: rollSkillEpochTarget());
      await _persist();
      return;
    }
    try {
      final m = jsonDecode(raw);
      if (m is Map<String, dynamic>) {
        state = SkillState.fromJson(m);
      } else if (m is Map) {
        state = SkillState.fromJson(Map<String, dynamic>.from(m));
      }
      // Migrate v1 prefs missing epoch fields.
      if (!raw.contains('epoch_target_n')) {
        state = state.copyWith(
          version: 2,
          epochTargetN: rollSkillEpochTarget(),
          epochMeans: const [],
        );
        await _persist();
      }
    } catch (_) {
      state = SkillState(epochTargetN: rollSkillEpochTarget());
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

  /// Push current in-block mean into the epoch (if any scored takes).
  Future<double?> commitFocusBlockMean() async {
    if (state.blockN <= 0) {
      state = state.copyWith(blockSum: 0, blockN: 0);
      await _persist();
      return null;
    }
    final mean = state.blockSum / state.blockN;
    final means = List<double>.from(state.epochMeans)..add(mean);
    state = state.copyWith(epochMeans: means, blockSum: 0, blockN: 0);
    await _persist();
    return mean;
  }

  Future<void> resolveEpoch({required int newTargetN}) async {
    state = state.copyWith(
      epochMeans: const [],
      epochTargetN: newTargetN.clamp(kSkillEpochMinN, kSkillEpochMaxN),
    );
    await _persist();
  }

  Future<void> tickCooldown() async {
    final cd = state.cooldownBlocks;
    if (cd <= 0) return;
    state = state.copyWith(cooldownBlocks: cd - 1);
    await _persist();
  }

  Future<void> onBlockBoundary() async {
    await tickCooldown();
    state = state.copyWith(blockSum: 0, blockN: 0);
    await _persist();
  }

  double? dayMean(String dayKey) => state.days[dayKey]?.mean;

  int dayN(String dayKey) => state.days[dayKey]?.n ?? 0;
}
