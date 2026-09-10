/// design/212 — spoken-form cache + practice skill controller.
library;

import 'dart:convert';

import 'package:crypto/crypto.dart';

import '../api/client.dart';
import 'chunk_density.dart';
import 'skill_adapt.dart';
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
  PracticeSkillController({SkillStore? store}) : store = store ?? SkillStore();

  final SkillStore store;
  final SpokenCache spokenCache = SpokenCache();

  bool serverEnabled = true;
  bool cloudSttEnabled = true;
  AsrClient? _client;

  void attachClient(AsrClient client) => _client = client;

  void setServerFlags({required bool skill, required bool cloudStt}) {
    serverEnabled = skill;
    cloudSttEnabled = cloudStt && skill;
  }

  Future<void> bindUid(String? uid) => store.bindUid(uid);

  int get tier => store.state.tier;
  int get density => store.state.density;

  List<String> chunksFor(List<String> base) =>
      effectiveChunks(base, store.state.density);

  Future<String?> ensureSpoken(String chunkDisplay) async {
    final c = _client;
    if (c == null || !serverEnabled) return null;
    final hit = spokenCache.peek(chunkDisplay);
    if (hit != null) return hit;
    try {
      final r = await c.fetchSpokenText(chunkDisplay);
      if (r == null) return null;
      spokenCache.put(chunkDisplay, r.spoken, version: r.speakNormVersion);
      return r.spoken;
    } catch (_) {
      return null;
    }
  }

  /// Score take bytes via cloud STT against spoken reference. Local store only.
  Future<SkillScoreResult?> onTakeReady({
    required String chunkDisplay,
    required List<int> takeBytes,
    required String mime,
    required List<String> baseChunks,
  }) async {
    if (!serverEnabled || !cloudSttEnabled) return null;
    final c = _client;
    if (c == null || takeBytes.isEmpty) return null;
    final spoken = await ensureSpoken(chunkDisplay);
    if (spoken == null || spoken.trim().isEmpty) return null;
    String? heard;
    try {
      heard = await c.recognizePracticeTake(
        bytes: takeBytes,
        mime: mime,
      );
    } catch (_) {
      return null;
    }
    if (heard == null || heard.trim().isEmpty) {
      return const SkillScoreResult(ok: false, error: 'empty_heard');
    }
    final score = contentWordCoverage(spoken, heard);
    if (!score.ok || score.accuracy == null) return score;
    await store.addScored(score.accuracy!);
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
    }
    await store.onBlockBoundary();
  }
}
