/// design/412 - every time the practice rung is looked at or moved, one row.
///
/// The evidence log keeps seven days, so a rung that moved two weeks ago had no
/// record of why. These rows ride in the skill store the server already keeps.
library;

import 'skill_adapt.dart';
import 'skill_ladder.dart';

/// Rows kept per account. An epoch is 5 to 10 three-minute blocks, so this is
/// years of checks.
const int kSkillHistoryMax = 400;

/// Bumped when a rung has to be put back by hand. design/412 put back the
/// rung a killed sample round left behind.
const int kSkillLadderFix = 1;

class SkillChange {
  const SkillChange({
    required this.atMs,
    required this.reason,
    required this.tierBefore,
    required this.densityBefore,
    required this.tier,
    required this.density,
    this.avg,
    this.blocks = 0,
    this.lo = kSkillFinerThreshold,
    this.hi = kSkillCoarserThreshold,
  });

  final int atMs;

  /// An epoch reason from [decideSkillAdapt], or one of `sample_on`,
  /// `sample_back`, `sample_left`, `reset`.
  final String reason;
  final int tierBefore;
  final int densityBefore;
  final int tier;
  final int density;

  /// The epoch average that decided it. Null for rows no average decided.
  final double? avg;
  final int blocks;

  /// The two lines in force when the row was written, so a row from before a
  /// line moved still reads right.
  final double lo;
  final double hi;

  String get key => '$atMs:$reason';

  int get ladderBefore =>
      skillLadderDisplayN(tier: tierBefore, density: densityBefore);
  int get ladderAfter => skillLadderDisplayN(tier: tier, density: density);

  Map<String, dynamic> toJson() => {
        'at': atMs,
        'why': reason,
        't0': tierBefore,
        'd0': densityBefore,
        't1': tier,
        'd1': density,
        if (avg != null) 'avg': avg,
        'n': blocks,
        'lo': lo,
        'hi': hi,
      };

  static SkillChange? fromJson(Object? raw) {
    if (raw is! Map) return null;
    final at = (raw['at'] as num?)?.toInt() ?? 0;
    final why = '${raw['why'] ?? ''}'.trim();
    if (at <= 0 || why.isEmpty) return null;
    int tierOf(Object? v) => ((v as num?)?.toInt() ?? 2).clamp(0, 9);
    int densityOf(Object? v) => ((v as num?)?.toInt() ?? 0).clamp(-2, 2);
    final avg = (raw['avg'] as num?)?.toDouble();
    return SkillChange(
      atMs: at,
      reason: why,
      tierBefore: tierOf(raw['t0']),
      densityBefore: densityOf(raw['d0']),
      tier: tierOf(raw['t1']),
      density: densityOf(raw['d1']),
      avg: avg?.clamp(0.0, 1.0),
      blocks: ((raw['n'] as num?)?.toInt() ?? 0).clamp(0, 1000),
      lo: ((raw['lo'] as num?)?.toDouble() ?? kSkillFinerThreshold)
          .clamp(0.0, 1.0),
      hi: ((raw['hi'] as num?)?.toDouble() ?? kSkillCoarserThreshold)
          .clamp(0.0, 1.0),
    );
  }
}

List<SkillChange> parseSkillHistory(Object? raw) {
  if (raw is! List) return const [];
  final out = <SkillChange>[];
  for (final row in raw) {
    final c = SkillChange.fromJson(row);
    if (c != null) out.add(c);
  }
  return trimSkillHistory(out);
}

/// Oldest first, one row per key, at most [kSkillHistoryMax].
List<SkillChange> trimSkillHistory(List<SkillChange> rows) {
  final byKey = <String, SkillChange>{};
  for (final r in rows) {
    byKey[r.key] = r;
  }
  final out = byKey.values.toList()..sort((a, b) => a.atMs.compareTo(b.atMs));
  if (out.length <= kSkillHistoryMax) return out;
  return out.sublist(out.length - kSkillHistoryMax);
}

/// Two devices each keep their own rows, so a merge is the union.
List<SkillChange> mergeSkillHistory(
  List<SkillChange> a,
  List<SkillChange> b,
) =>
    trimSkillHistory([...a, ...b]);

String skillChangeReasonKo(String reason) {
  switch (reason) {
    case 'hold':
      return '그대로';
    case 'finer':
      return '구간 잘게 (쉽게)';
    case 'coarser':
      return '구간 크게 (어렵게)';
    case 'tier_up':
      return '속도 등급 올림';
    case 'tier_down':
      return '속도 등급 내림';
    case 'floor':
      return '가장 쉬움이라 그대로';
    case 'ceiling':
      return '가장 어려움이라 그대로';
    case 'sample_on':
      return '발음 표본 시작 (고정)';
    case 'sample_back':
      return '발음 표본 끝, 원래 난이도로';
    case 'sample_left':
      return '꺼진 표본 정리, 원래 난이도로';
    case 'reset':
      return '난이도 되돌림';
    default:
      return reason;
  }
}
