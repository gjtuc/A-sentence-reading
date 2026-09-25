/// design/364 — which chunks of each difficulty round have been recorded.
library;

import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import 'sample_corpus.dart';

/// v2 holds coverage. v1 counted takes and called a round done at a third of it.
const String kSampleRoundsPrefsKeyBase = 'asr.sample_rounds.v2';

String sampleRoundsPrefsKey(String? uid) {
  final u = (uid ?? '').trim();
  if (u.isEmpty) return kSampleRoundsPrefsKeyBase;
  return '$kSampleRoundsPrefsKeyBase.$u';
}

/// Chunks the round asks for, summed over its lines.
///
/// A sentence is read one growing chunk at a time, so counting sentences would
/// report a round collected while most of it was still unspoken.
int sampleRoundTarget(int round) =>
    sampleLinesForRound(round).fold(0, (n, line) => n + line.chunks.length);

/// Key for one asked-for chunk, e.g. `sent_f07:1`.
String sampleChunkKey({required String lineId, required int chunkIndex}) =>
    '${lineId.trim()}:$chunkIndex';

/// Chunks already recorded, per round.
///
/// Coverage rather than a take count: saying one chunk five times is one chunk
/// collected, and a round abandoned early cannot read as done.
class SampleRounds {
  const SampleRounds({this.covered = const {}});

  final Map<int, Set<String>> covered;

  int takesFor(int round) => covered[round]?.length ?? 0;

  bool isDone(int round) => takesFor(round) >= sampleRoundTarget(round);

  int get doneCount {
    var n = 0;
    for (var r = 1; r <= kSampleRoundCount; r++) {
      if (isDone(r)) n += 1;
    }
    return n;
  }

  SampleRounds addChunk(int round, String key) {
    final k = key.trim();
    if (round < 1 || round > kSampleRoundCount || k.isEmpty) return this;
    if (covered[round]?.contains(k) ?? false) return this;
    final next = <int, Set<String>>{
      for (final e in covered.entries) e.key: Set<String>.from(e.value),
    };
    (next[round] ??= <String>{}).add(k);
    return SampleRounds(covered: next);
  }

  Map<String, dynamic> toJson() => {
        'covered': {
          for (final e in covered.entries)
            '${e.key}': (e.value.toList()..sort()),
        },
      };

  static SampleRounds fromJson(Map<String, dynamic>? m) {
    final raw = m?['covered'];
    if (raw is! Map) return const SampleRounds();
    final out = <int, Set<String>>{};
    for (final e in raw.entries) {
      final r = int.tryParse('${e.key}');
      if (r == null || r < 1 || r > kSampleRoundCount) continue;
      final v = e.value;
      if (v is! List) continue;
      final keys = <String>{
        for (final k in v)
          if ('$k'.trim().isNotEmpty) '$k'.trim(),
      };
      if (keys.isNotEmpty) out[r] = keys;
    }
    return SampleRounds(covered: out);
  }
}

Future<SampleRounds> loadSampleRounds(String? uid) async {
  try {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(sampleRoundsPrefsKey(uid));
    if (raw == null || raw.isEmpty) return const SampleRounds();
    final m = jsonDecode(raw);
    if (m is Map<String, dynamic>) return SampleRounds.fromJson(m);
    if (m is Map) return SampleRounds.fromJson(Map<String, dynamic>.from(m));
  } catch (_) {}
  return const SampleRounds();
}

Future<SampleRounds> noteSampleRoundTake(
  String? uid,
  int round, {
  required String lineId,
  required int chunkIndex,
}) async {
  final cur = await loadSampleRounds(uid);
  final next = cur.addChunk(
    round,
    sampleChunkKey(lineId: lineId, chunkIndex: chunkIndex),
  );
  if (next.takesFor(round) == cur.takesFor(round)) return cur;
  try {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      sampleRoundsPrefsKey(uid),
      jsonEncode(next.toJson()),
    );
  } catch (_) {
    return cur;
  }
  return next;
}

Future<void> clearSampleRounds(String? uid) async {
  try {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(sampleRoundsPrefsKey(uid));
  } catch (_) {}
}
