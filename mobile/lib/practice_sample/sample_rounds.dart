/// design/364 — how many sample takes each difficulty round has collected.
library;

import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import 'sample_corpus.dart';

const String kSampleRoundsPrefsKeyBase = 'asr.sample_rounds.v1';

String sampleRoundsPrefsKey(String? uid) {
  final u = (uid ?? '').trim();
  if (u.isEmpty) return kSampleRoundsPrefsKeyBase;
  return '$kSampleRoundsPrefsKeyBase.$u';
}

/// Takes needed before a round counts as done (twelve fixed + three fresh).
int sampleRoundTarget(int round) => sampleLinesForRound(round).length;

/// Takes per round, keyed by round number.
///
/// A round is counted in takes rather than in "opened it once", so a round
/// abandoned after two sentences does not read as collected.
class SampleRounds {
  const SampleRounds({this.takes = const {}});

  final Map<int, int> takes;

  int takesFor(int round) => takes[round] ?? 0;

  bool isDone(int round) => takesFor(round) >= sampleRoundTarget(round);

  int get doneCount {
    var n = 0;
    for (var r = 1; r <= kSampleRoundCount; r++) {
      if (isDone(r)) n += 1;
    }
    return n;
  }

  SampleRounds addTake(int round) {
    if (round < 1 || round > kSampleRoundCount) return this;
    final next = Map<int, int>.from(takes);
    next[round] = (next[round] ?? 0) + 1;
    return SampleRounds(takes: next);
  }

  Map<String, dynamic> toJson() => {
        'takes': {for (final e in takes.entries) '${e.key}': e.value},
      };

  static SampleRounds fromJson(Map<String, dynamic>? m) {
    final raw = m?['takes'];
    if (raw is! Map) return const SampleRounds();
    final out = <int, int>{};
    for (final e in raw.entries) {
      final r = int.tryParse('${e.key}');
      final v = e.value;
      if (r == null || r < 1 || r > kSampleRoundCount) continue;
      final n = v is num ? v.toInt() : int.tryParse('$v');
      if (n == null || n <= 0) continue;
      out[r] = n;
    }
    return SampleRounds(takes: out);
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

Future<SampleRounds> noteSampleRoundTake(String? uid, int round) async {
  final cur = await loadSampleRounds(uid);
  final next = cur.addTake(round);
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
