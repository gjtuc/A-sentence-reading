import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:sentence_reading/practice_sample/sample_corpus.dart';
import 'package:sentence_reading/practice_sample/sample_round_sheet.dart';
import 'package:sentence_reading/practice_sample/sample_rounds.dart';
import 'package:sentence_reading/practice_sample/sample_seed.dart';
import 'package:sentence_reading/practice_skill/skill_adapt.dart';
import 'package:sentence_reading/practice_skill/skill_store.dart';

void main() {
  test('every sample line breaks into growing chunks ending in the sentence',
      () {
    for (final line in sampleAllLines) {
      final segments = line.segments;
      expect(segments.length, greaterThanOrEqualTo(2),
          reason: '${line.id} needs at least one break');
      final chunks = line.chunks;
      expect(chunks.length, segments.length, reason: line.id);
      expect(chunks.last, line.text, reason: line.id);
      for (var i = 1; i < chunks.length; i++) {
        expect(chunks[i].startsWith(chunks[i - 1]), isTrue,
            reason: '${line.id} step $i must extend the one before');
        expect(chunks[i].length, greaterThan(chunks[i - 1].length),
            reason: '${line.id} step $i must add words');
      }
      expect(line.text.contains(kSampleBreak), isFalse, reason: line.id);
      expect(line.text.trim(), line.text, reason: line.id);
    }
  });

  test('sample line ids are unique and the sets are the sizes rounds expect',
      () {
    final ids = sampleAllLines.map((e) => e.id).toList();
    expect(ids.toSet().length, ids.length);
    expect(kSampleFixedLines.length, 12);
    expect(kSampleFreshLines.length, 30);
    for (var r = 1; r <= kSampleRoundCount; r++) {
      expect(sampleFreshForRound(r).length, 3, reason: 'round $r');
      expect(sampleLinesForRound(r).length, 15, reason: 'round $r');
    }
    // Every fresh line is spent exactly once across the ten rounds.
    final spent = <String>[];
    for (var r = 1; r <= kSampleRoundCount; r++) {
      spent.addAll(sampleFreshForRound(r).map((e) => e.id));
    }
    expect(spent.length, kSampleFreshLines.length);
    expect(spent.toSet().length, spent.length);
  });

  test('the chunk plan carries one ready row per sentence', () {
    final plan = sampleChunkPlan();
    expect(plan['status'], 'ok');
    final sentences = plan['sentences'] as Map<String, dynamic>;
    expect(sentences.length, sampleAllLines.length);
    final session = sampleSessionJson();
    final rows = session['sentences'] as List<dynamic>;
    expect(rows.length, sampleAllLines.length);
    for (final row in rows) {
      final m = row as Map<String, dynamic>;
      final sid = m['id'] as String;
      // A plan row missing for a session sentence makes practice skip it.
      expect(sentences.containsKey(sid), isTrue, reason: sid);
      final chunks = (sentences[sid] as Map)['chunks'] as List<dynamic>;
      expect(chunks.isNotEmpty, isTrue, reason: sid);
      expect(chunks.last, m['text'], reason: sid);
      // The title aligner rewrites `title` rows, which would break the match.
      expect(m['section'], isNot('title'), reason: sid);
    }
  });

  test('rounds map onto the ten ladder tiers', () {
    expect(sampleRoundTier(1), 0);
    expect(sampleRoundTier(kSampleRoundCount), 9);
    expect(sampleRoundTier(0), 0);
    expect(sampleRoundTier(99), 9);
    var last = -1;
    for (var r = 1; r <= kSampleRoundCount; r++) {
      final n = sampleRoundLadderN(r);
      expect(n, greaterThan(last), reason: 'round $r must be harder');
      last = n;
    }
  });

  test('a pinned ladder is not moved by the epoch', () {
    const base = ['one two three four', 'one two three four five six seven'];
    const easy = SkillState(
      pinned: true,
      tier: 9,
      density: 0,
      epochMeans: [0.2, 0.2, 0.2, 0.2, 0.2],
      epochTargetN: 5,
    );
    final downhill = decideSkillAdapt(state: easy, baseChunks: base);
    expect(downhill.reason, 'pinned');
    expect(downhill.tierDelta, 0);
    expect(downhill.densityDelta, 0);
    const perfect = SkillState(
      pinned: true,
      tier: 0,
      density: 0,
      epochMeans: [1, 1, 1, 1, 1],
      epochTargetN: 5,
    );
    final uphill = decideSkillAdapt(state: perfect, baseChunks: base);
    expect(uphill.reason, 'pinned');
    final applied = resolveSkillAdaptApply(state: perfect, decision: uphill);
    expect(applied.changed, isFalse);
    expect(applied.tier, 0);
  });

  test('an unpinned ladder goes back to the rung it left', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final store = SkillStore();
    await store.bindUid('u1');
    await store.setTierDensity(tier: 3, density: -1);
    await store.pinLadder(tier: 9, density: 2);
    expect(store.state.pinned, isTrue);
    expect(store.state.tier, 9);
    expect(store.state.density, 2);
    // A hard sweep must not report itself as a drop in today's skill.
    await store.addScored(0.2);
    expect(store.state.days.isEmpty, isTrue);
    expect(store.state.blockN, 1);
    await store.unpinLadder();
    expect(store.state.pinned, isFalse);
    expect(store.state.tier, 3);
    expect(store.state.density, -1);
    expect(store.state.epochMeans, isEmpty);
    await store.addScored(0.9);
    expect(store.state.days.isEmpty, isFalse);
  });

  test('a pin left by a kill is dropped on the next bind', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final first = SkillStore();
    await first.bindUid('u1');
    await first.setTierDensity(tier: 2, density: 0);
    await first.pinLadder(tier: 8, density: 0);
    expect(first.state.tier, 8);

    final afterRestart = SkillStore();
    await afterRestart.bindUid('u1');
    expect(afterRestart.state.pinned, isFalse);
    expect(afterRestart.state.tier, 2);
  });

  test('a round counts as done only once its takes are in', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    expect(sampleRoundTarget(1), 15);
    var rounds = await loadSampleRounds('u1');
    expect(rounds.isDone(1), isFalse);
    for (var i = 0; i < sampleRoundTarget(1) - 1; i++) {
      rounds = await noteSampleRoundTake('u1', 1);
    }
    expect(rounds.isDone(1), isFalse);
    expect(rounds.doneCount, 0);
    rounds = await noteSampleRoundTake('u1', 1);
    expect(rounds.isDone(1), isTrue);
    expect(rounds.doneCount, 1);
    // A round outside 1..10 must not create a phantom entry.
    rounds = await noteSampleRoundTake('u1', 44);
    expect(rounds.takesFor(44), 0);
  });
}
