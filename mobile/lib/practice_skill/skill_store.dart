/// design/212+215 — local accuracy samples + day aggregates + epoch means.
library;

import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../api/focus_practice_models.dart';
import '../api/practice_cloud_hooks.dart';
import 'chunk_density.dart';
import 'skill_adapt.dart';
import 'skill_ladder.dart';

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
    this.updatedAtMs = 0,
    this.pinned = false,
    this.savedTier = -1,
    this.savedDensity = 0,
  });

  final int version;
  final int tier; // 0..5
  final int density; // -2..2
  /// design/364 — hold this rung; the epoch must not move it.
  final bool pinned;

  /// Rung to come back to when the pin is lifted (-1 = nothing held).
  final int savedTier;
  final int savedDensity;
  final Map<String, SkillDayAgg> days;
  final double blockSum;
  final int blockN;
  final int cooldownBlocks;
  /// Completed focus-block means awaiting epoch resolve (design/215).
  final List<double> epochMeans;
  final int epochTargetN;
  /// design/250 — LWW stamp for live fields.
  final int updatedAtMs;

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
    int? updatedAtMs,
    bool? pinned,
    int? savedTier,
    int? savedDensity,
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
      updatedAtMs: updatedAtMs ?? this.updatedAtMs,
      pinned: pinned ?? this.pinned,
      savedTier: savedTier ?? this.savedTier,
      savedDensity: savedDensity ?? this.savedDensity,
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
        'pinned': pinned,
        'saved_tier': savedTier,
        'saved_density': savedDensity,
        'updated_at_ms': updatedAtMs < 0 ? 0 : updatedAtMs,
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
      tier: ((m['tier'] as num?)?.toInt() ?? 2).clamp(0, 9),
      density: ((m['density'] as num?)?.toInt() ?? 0).clamp(-2, 2),
      days: days,
      blockSum: (m['block_sum'] as num?)?.toDouble() ?? 0,
      blockN: (m['block_n'] as num?)?.toInt() ?? 0,
      cooldownBlocks: (m['cooldown_blocks'] as num?)?.toInt() ?? 0,
      epochMeans: means,
      epochTargetN: target,
      pinned: m['pinned'] == true,
      savedTier: ((m['saved_tier'] as num?)?.toInt() ?? -1).clamp(-1, 9),
      savedDensity: ((m['saved_density'] as num?)?.toInt() ?? 0).clamp(-2, 2),
      updatedAtMs: (() {
        final u = (m['updated_at_ms'] as num?)?.toInt() ?? 0;
        return u < 0 ? 0 : u;
      })(),
    );
  }
}

class SkillStore {
  String? _uid;
  SkillState state = SkillState(epochTargetN: rollSkillEpochTarget());

  Future<void> bindUid(String? uid) async {
    _uid = uid;
    await asrPracticeEnsurePulled?.call();
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(skillPrefsKey(_uid));
    if (raw == null || raw.isEmpty) {
      state = SkillState(epochTargetN: rollSkillEpochTarget());
      // Cache empty local without cloud push (avoid LWW clobber of remote).
      await prefs.setString(skillPrefsKey(_uid), jsonEncode(state.toJson()));
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
    // design/364 — a pin is only good while the sample round is on screen. One
    // that survived a kill would silently hold every later paper on that rung,
    // so every bind drops it; a starting round re-pins right after this.
    if (state.pinned) {
      await unpinLadder();
    }
  }

  Future<void> _persist() async {
    state = state.copyWith(
      updatedAtMs: DateTime.now().millisecondsSinceEpoch,
    );
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(skillPrefsKey(_uid), jsonEncode(state.toJson()));
    asrSchedulePushSkill?.call(state.toJson());
  }

  Future<void> addScored(double accuracy, {String? dayKey}) async {
    // design/364 — a pinned sweep deliberately runs rungs the speaker cannot
    // reach. Folding a 20% hard round into the day would report a skill drop
    // that did not happen, so only the block accumulator sees it.
    if (state.pinned) {
      state = state.copyWith(
        blockSum: state.blockSum + accuracy,
        blockN: state.blockN + 1,
      );
      await _persist();
      return;
    }
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

  /// Hold [tier]/[density] until [unpinLadder], remembering the current rung.
  Future<void> pinLadder({required int tier, required int density}) async {
    final keepTier = state.pinned ? state.savedTier : state.tier;
    final keepDensity = state.pinned ? state.savedDensity : state.density;
    state = state.copyWith(
      pinned: true,
      savedTier: keepTier,
      savedDensity: keepDensity,
      tier: clampSkillTier(tier),
      density: clampChunkDensity(density),
      cooldownBlocks: 0,
      epochMeans: const [],
      blockSum: 0,
      blockN: 0,
    );
    await _persist();
  }

  /// Put the remembered rung back and drop everything the sweep accumulated.
  Future<void> unpinLadder() async {
    if (!state.pinned) return;
    final back = state.savedTier;
    state = state.copyWith(
      pinned: false,
      tier: back < 0 ? state.tier : clampSkillTier(back),
      density: back < 0 ? state.density : clampChunkDensity(state.savedDensity),
      savedTier: -1,
      savedDensity: 0,
      cooldownBlocks: 0,
      epochMeans: const [],
      blockSum: 0,
      blockN: 0,
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
