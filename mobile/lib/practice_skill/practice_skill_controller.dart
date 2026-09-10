/// design/212 — spoken-form cache + practice skill controller (+213 evidence).
library;

import 'dart:convert';

import 'package:crypto/crypto.dart';

import '../api/client.dart';
import 'chunk_density.dart';
import 'skill_adapt.dart';
import 'skill_evidence.dart';
import '../practice_rhythm/judgment_tier.dart';
import 'skill_score.dart';
import 'skill_store.dart';

class SpokenCache {
  String speakNorm = 'v2';
  final Map<String, String> _map = {};

  void setSpeakNorm(String v) {
    final n = v.trim();
    if (n.isEmpty || n == speakNorm) return;
    speakNorm = n;
    _map.clear();
  }

  String _key(String chunk) {
    final digest = sha256.convert(utf8.encode(chunk.trim()));
    return '$speakNorm|${digest.toString().substring(0, 24)}';
  }

  String? peek(String chunk) => _map[_key(chunk)];

  void put(String chunk, String spoken, {String? version}) {
    if (version != null && version.trim().isNotEmpty) {
      setSpeakNorm(version.trim());
    }
    _map[_key(chunk)] = spoken;
  }

  void clear() => _map.clear();
}

class PracticeSkillController {
  PracticeSkillController({
    SkillStore? store,
    SkillEvidenceEmitter? evidence,
  })  : store = store ?? SkillStore(),
        evidence = evidence ?? SkillEvidenceEmitter();

  final SkillStore store;
  final SkillEvidenceEmitter evidence;
  final SpokenCache spokenCache = SpokenCache();

  bool serverEnabled = true;
  bool cloudSttEnabled = true;
  bool evidenceEnabled = true;
  AsrClient? _client;
  String _cacheId = '';
  String _sentenceId = '';
  int _chunkIndex = 0;
  int _focusElapsedMs = 0;

  void attachClient(AsrClient client) {
    _client = client;
    evidence.attachClient(client);
  }

  void setServerFlags({
    required bool skill,
    required bool cloudStt,
    bool? skillEvidence,
  }) {
    serverEnabled = skill;
    cloudSttEnabled = cloudStt && skill;
    evidenceEnabled = (skillEvidence ?? evidenceEnabled) && skill;
    evidence.setEnabled(evidenceEnabled);
  }

  void setCycleContext({
    required String cacheId,
    required String sentenceId,
    required int chunkIndex,
    required int focusElapsedMs,
  }) {
    _cacheId = cacheId;
    _sentenceId = sentenceId;
    _chunkIndex = chunkIndex;
    _focusElapsedMs = focusElapsedMs;
  }

  Future<void> bindUid(String? uid) async {
    await store.bindUid(uid);
    await evidence.bindUid(uid);
  }

  int get tier => store.state.tier;
  int get density => store.state.density;

  List<String> chunksFor(List<String> base) =>
      effectiveChunks(base, store.state.density);

  Future<String?> ensureSpoken(String chunkDisplay) async {
    final c = _client;
    if (c == null || !serverEnabled) return null;
    final hit = spokenCache.peek(chunkDisplay);
    if (hit != null) {
      await evidence.emit(
        kind: 'practice_skill_spoken',
        cacheId: _cacheId,
        ok: true,
        code: 'cache_hit',
        details: {
          'phase': 'spoken',
          'cache_hit': 1,
          'speak_norm': spokenCache.speakNorm.replaceAll('.', '_'),
          'chunk_index': _chunkIndex,
          'sentence_id_h16': skillSentenceIdH16(_sentenceId),
          'focus_elapsed_ms': _focusElapsedMs,
        },
      );
      return hit;
    }
    final sw = Stopwatch()..start();
    try {
      final r = await c.fetchSpokenText(chunkDisplay);
      sw.stop();
      if (r == null) {
        await evidence.emit(
          kind: 'practice_skill_spoken',
          cacheId: _cacheId,
          ok: false,
          code: 'spoken_null',
          details: {
            'phase': 'spoken',
            'cache_hit': 0,
            'spoken_ms': sw.elapsedMilliseconds,
            'chunk_index': _chunkIndex,
            'sentence_id_h16': skillSentenceIdH16(_sentenceId),
          },
        );
        return null;
      }
      spokenCache.put(chunkDisplay, r.spoken, version: r.speakNormVersion);
      await evidence.emit(
        kind: 'practice_skill_spoken',
        cacheId: _cacheId,
        ok: true,
        code: 'spoken_ok',
        details: {
          'phase': 'spoken',
          'cache_hit': 0,
          'spoken_ms': sw.elapsedMilliseconds,
          'speak_norm': r.speakNormVersion.replaceAll('.', '_'),
          'chunk_index': _chunkIndex,
          'sentence_id_h16': skillSentenceIdH16(_sentenceId),
          'focus_elapsed_ms': _focusElapsedMs,
        },
      );
      return r.spoken;
    } catch (_) {
      sw.stop();
      await evidence.emit(
        kind: 'practice_skill_spoken',
        cacheId: _cacheId,
        ok: false,
        code: 'spoken_fail',
        details: {
          'phase': 'spoken',
          'cache_hit': 0,
          'spoken_ms': sw.elapsedMilliseconds,
          'chunk_index': _chunkIndex,
          'sentence_id_h16': skillSentenceIdH16(_sentenceId),
        },
      );
      return null;
    }
  }

  Future<SkillScoreResult?> onTakeReady({
    required String chunkDisplay,
    required List<int> takeBytes,
    required String mime,
    required List<String> baseChunks,
  }) async {
    if (!serverEnabled) {
      await evidence.emit(
        kind: 'practice_skill_unscored',
        cacheId: _cacheId,
        ok: false,
        code: 'skill_off',
        details: {
          'phase': 'unscored',
          'reason': 'skill_off',
          'chunk_index': _chunkIndex,
        },
      );
      return null;
    }
    if (!cloudSttEnabled) {
      await evidence.emit(
        kind: 'practice_skill_unscored',
        cacheId: _cacheId,
        ok: false,
        code: 'stt_cloud_off',
        details: {
          'phase': 'unscored',
          'reason': 'stt_cloud_off',
          'take_bytes': takeBytes.length,
          'chunk_index': _chunkIndex,
        },
      );
      return null;
    }
    final c = _client;
    if (c == null || takeBytes.isEmpty) {
      await evidence.emit(
        kind: 'practice_skill_unscored',
        cacheId: _cacheId,
        ok: false,
        code: 'no_take',
        details: {
          'phase': 'unscored',
          'reason': 'no_take',
          'take_bytes': takeBytes.length,
          'chunk_index': _chunkIndex,
        },
      );
      return null;
    }
    final spoken = await ensureSpoken(chunkDisplay);
    if (spoken == null || spoken.trim().isEmpty) {
      await evidence.emit(
        kind: 'practice_skill_unscored',
        cacheId: _cacheId,
        ok: false,
        code: 'no_spoken',
        details: {
          'phase': 'unscored',
          'reason': 'no_spoken',
          'take_bytes': takeBytes.length,
          'chunk_index': _chunkIndex,
        },
      );
      return null;
    }
    final sttSw = Stopwatch()..start();
    String? heard;
    try {
      heard = await c.recognizePracticeTake(
        bytes: takeBytes,
        mime: mime,
      );
      sttSw.stop();
      await evidence.emit(
        kind: 'practice_skill_stt',
        cacheId: _cacheId,
        ok: heard != null && heard.trim().isNotEmpty,
        code: (heard != null && heard.trim().isNotEmpty) ? 'stt_ok' : 'stt_empty',
        details: {
          'phase': 'stt',
          'engine': 'gemini',
          'stt_ms': sttSw.elapsedMilliseconds,
          'take_bytes': takeBytes.length,
          'chunk_index': _chunkIndex,
          'chunk_n': baseChunks.isEmpty
              ? 0
              : effectiveChunks(baseChunks, store.state.density).length,
          'sentence_id_h16': skillSentenceIdH16(_sentenceId),
          'density': store.state.density,
          'tier': store.state.tier,
          'focus_elapsed_ms': _focusElapsedMs,
        },
      );
    } catch (_) {
      sttSw.stop();
      await evidence.emit(
        kind: 'practice_skill_stt',
        cacheId: _cacheId,
        ok: false,
        code: 'stt_fail',
        details: {
          'phase': 'stt',
          'engine': 'gemini',
          'stt_ms': sttSw.elapsedMilliseconds,
          'take_bytes': takeBytes.length,
          'chunk_index': _chunkIndex,
          'reason': 'stt_fail',
        },
      );
      await evidence.emit(
        kind: 'practice_skill_unscored',
        cacheId: _cacheId,
        ok: false,
        code: 'stt_fail',
        details: {
          'phase': 'unscored',
          'reason': 'stt_fail',
          'take_bytes': takeBytes.length,
          'chunk_index': _chunkIndex,
        },
      );
      return null;
    }
    if (heard == null || heard.trim().isEmpty) {
      await evidence.emit(
        kind: 'practice_skill_unscored',
        cacheId: _cacheId,
        ok: false,
        code: 'empty_heard',
        details: {
          'phase': 'unscored',
          'reason': 'empty_heard',
          'take_bytes': takeBytes.length,
          'chunk_index': _chunkIndex,
        },
      );
      return const SkillScoreResult(ok: false, error: 'empty_heard');
    }
    final score = contentWordCoverage(spoken, heard);
    if (!score.ok || score.accuracy == null) {
      await evidence.emit(
        kind: 'practice_skill_unscored',
        cacheId: _cacheId,
        ok: false,
        code: score.error ?? 'score_fail',
        details: {
          'phase': 'unscored',
          'reason': (score.error ?? 'score_fail').replaceAll('-', '_'),
          'ref_n': score.refN,
          'hit_n': score.hitN,
          'list_v': score.listV,
          'chunk_index': _chunkIndex,
          'density': store.state.density,
          'tier': store.state.tier,
        },
      );
      return score;
    }
    await store.addScored(score.accuracy!);
    final acc = score.accuracy!;
    // design/214 — enum only (no cheer copy string).
    final judgmentTier = judgmentTierKey(judgmentTierFor(acc));
    await evidence.emit(
      kind: 'practice_skill_scored',
      cacheId: _cacheId,
      ok: true,
      code: 'scored',
      details: {
        'phase': 'scored',
        'accuracy': acc,
        'accuracy_pct': (acc * 100).round(),
        'accuracy_bin': accuracyBin(acc),
        'judgment_tier': judgmentTier,
        'ref_n': score.refN,
        'hit_n': score.hitN,
        'list_v': score.listV,
        'density': store.state.density,
        'tier': store.state.tier,
        'block_n': store.state.blockN,
        'cooldown': store.state.cooldownBlocks,
        'can_finer': canFiner(baseChunks, store.state.density) ? 1 : 0,
        'can_coarser': canCoarser(baseChunks, store.state.density) ? 1 : 0,
        'chunk_index': _chunkIndex,
        'chunk_n': effectiveChunks(baseChunks, store.state.density).length,
        'sentence_id_h16': skillSentenceIdH16(_sentenceId),
        'speak_norm': spokenCache.speakNorm.replaceAll('.', '_'),
        'take_bytes': takeBytes.length,
        'focus_elapsed_ms': _focusElapsedMs,
      },
    );
    final decision = decideSkillAdapt(
      state: store.state,
      baseChunks: baseChunks,
    );
    if (decision.densityDelta != 0 || decision.tierDelta != 0) {
      final newDens =
          clampChunkDensity(store.state.density + decision.densityDelta);
      final newTier = (store.state.tier + decision.tierDelta).clamp(0, 5);
      await store.setTierDensity(
        tier: newTier,
        density: decision.densityDelta != 0 ? newDens : store.state.density,
        cooldown: decision.tierDelta != 0 ? 1 : store.state.cooldownBlocks,
      );
      if (decision.densityDelta != 0 || decision.tierDelta != 0) {
        await store.resetBlockAccum();
      }
      await evidence.emit(
        kind: 'practice_skill_adapt',
        cacheId: _cacheId,
        ok: true,
        code: decision.reason,
        details: {
          'phase': 'adapt',
          'reason': decision.reason,
          'density_delta': decision.densityDelta,
          'tier_delta': decision.tierDelta,
          'density': store.state.density,
          'tier': store.state.tier,
          'can_finer': canFiner(baseChunks, store.state.density) ? 1 : 0,
          'can_coarser': canCoarser(baseChunks, store.state.density) ? 1 : 0,
          'block_n': store.state.blockN,
          'chunk_index': _chunkIndex,
          'sentence_id_h16': skillSentenceIdH16(_sentenceId),
          'focus_elapsed_ms': _focusElapsedMs,
        },
      );
    } else {
      await evidence.emit(
        kind: 'practice_skill_adapt',
        cacheId: _cacheId,
        ok: true,
        code: decision.reason,
        details: {
          'phase': 'adapt',
          'reason': decision.reason,
          'density_delta': 0,
          'tier_delta': 0,
          'density': store.state.density,
          'tier': store.state.tier,
          'block_n': store.state.blockN,
          'can_finer': canFiner(baseChunks, store.state.density) ? 1 : 0,
          'can_coarser': canCoarser(baseChunks, store.state.density) ? 1 : 0,
          'chunk_index': _chunkIndex,
        },
      );
    }
    return score;
  }

  Future<void> onFocusBlockDone(List<String> baseChunks) async {
    if (!serverEnabled) return;
    final decision = decideSkillAdapt(
      state: store.state,
      baseChunks: baseChunks,
    );
    if (decision.densityDelta != 0 || decision.tierDelta != 0) {
      await store.setTierDensity(
        tier: (store.state.tier + decision.tierDelta).clamp(0, 5),
        density: clampChunkDensity(
          store.state.density + decision.densityDelta,
        ),
        cooldown: decision.tierDelta != 0 ? 1 : 0,
      );
      await evidence.emit(
        kind: 'practice_skill_adapt',
        cacheId: _cacheId,
        ok: true,
        code: decision.reason,
        details: {
          'phase': 'block_adapt',
          'reason': decision.reason,
          'density_delta': decision.densityDelta,
          'tier_delta': decision.tierDelta,
          'density': store.state.density,
          'tier': store.state.tier,
        },
      );
    }
    await store.onBlockBoundary();
  }

  Future<void> flushEvidence({String cacheId = ''}) =>
      evidence.flush(cacheId: cacheId.isEmpty ? _cacheId : cacheId);

  void resetSessionSeq() => evidence.resetSessionSeq();
}
