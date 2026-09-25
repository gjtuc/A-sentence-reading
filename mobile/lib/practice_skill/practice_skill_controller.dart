/// design/212 — spoken-form cache + practice skill controller (+213 evidence).
library;

import 'dart:async';
import 'dart:convert';

import 'package:crypto/crypto.dart';

import '../api/client.dart';
import '../practice_rhythm/follow_span.dart';
import 'chunk_density.dart';
import 'skill_adapt.dart';
import 'skill_evidence.dart';
import '../practice_rhythm/judgment_tier.dart';
import 'skill_score.dart';
import 'skill_store.dart';
import 'spoken_disk_cache.dart';

class SpokenAlignMark {
  const SpokenAlignMark({
    this.code = 'unknown',
    this.tokenI = -1,
    this.cursor = -1,
    this.displayChars = -1,
    this.spokenChars = -1,
    this.tokenLen = -1,
    this.pieceLen = -1,
    this.differAt = -1,
    this.tokenShape = 'none',
    this.pieceClass = 'none',
    this.fullClass = 'none',
    this.gapLen = -1,
    this.gapShape = 'none',
    this.matchedN = -1,
    this.tailN = -1,
    this.renamedN = -1,
    this.phoneCode = 'none',
    this.phoneWordN = -1,
    this.phoneIpaN = -1,
    this.phoneWeightN = -1,
    this.phoneFilledN = -1,
    this.phoneEspeak = -1,
    this.phonePairs = '',
  });

  final String code;
  final int tokenI;
  final int cursor;
  final int displayChars;
  final int spokenChars;
  final int tokenLen;
  final int pieceLen;
  final int differAt;
  final String tokenShape;
  final String pieceClass;
  final String fullClass;
  final int gapLen;
  final String gapShape;
  final int matchedN;
  final int tailN;
  final int renamedN;
  final String phoneCode;
  final int phoneWordN;
  final int phoneIpaN;
  final int phoneWeightN;
  final int phoneFilledN;
  final int phoneEspeak;
  final String phonePairs;

  Map<String, Object?> get details => {
        'align_code': code,
        'align_token_i': tokenI,
        'align_cursor': cursor,
        'align_display_chars': displayChars,
        'align_spoken_chars': spokenChars,
        'token_len': tokenLen,
        'piece_len': pieceLen,
        'differ_at': differAt,
        'token_shape': tokenShape,
        'piece_class': pieceClass,
        'full_class': fullClass,
        'gap_len': gapLen,
        'gap_shape': gapShape,
        'matched_n': matchedN,
        'tail_n': tailN,
        'renamed_n': renamedN,
        'phone_code': phoneCode,
        'phone_word_n': phoneWordN,
        'phone_ipa_n': phoneIpaN,
        'phone_weight_n': phoneWeightN,
        'phone_filled_n': phoneFilledN,
        'phone_espeak': phoneEspeak,
        'phone_pairs': phonePairs,
      };
}

class SpokenCache {
  String speakNorm = 'v6';
  final Map<String, String> _map = {};
  final Map<String, List<FollowSpan>> _spans = {};
  final Map<String, SpokenAlignMark> _align = {};
  final SpokenDiskCache disk = SpokenDiskCache();

  void setSpeakNorm(String v) {
    final n = v.trim();
    if (n.isEmpty || n == speakNorm) return;
    speakNorm = n;
    _map.clear();
    _spans.clear();
    _align.clear();
  }

  String _key(String chunk) {
    final digest = sha256.convert(utf8.encode(chunk.trim()));
    return '$speakNorm|${digest.toString().substring(0, 24)}';
  }

  String? peek(String chunk) => _map[_key(chunk)];

  /// design/383 — rows saved on the phone skip the server round trip. A row
  /// made under another speak-norm version cannot be trusted, and [_key]
  /// already carries that version.
  /// Where the last [loadFromDisk] answer came from, for the evidence row:
  /// `memory`, `disk`, `disk_no_phones`, `disk_miss`, or `memory_no_phones`.
  String lastSource = 'none';

  int phoneSpanN(String chunk) {
    var n = 0;
    for (final span in peekSpans(chunk)) {
      if (span.phone.trim().isNotEmpty) n += 1;
    }
    return n;
  }

  bool _rowHasPhones(List<FollowSpan> spans) {
    if (spans.isEmpty) return true;
    return spans.any((span) => span.phone.trim().isNotEmpty);
  }

  Future<String?> loadFromDisk(String chunk) async {
    final key = _key(chunk);
    if (_map.containsKey(key)) {
      // A row kept in memory from before the symbols existed would otherwise be
      // served for the rest of the session, so it is dropped here too.
      if (!_rowHasPhones(_spans[key] ?? const [])) {
        lastSource = 'memory_no_phones';
        _map.remove(key);
        _spans.remove(key);
        _align.remove(key);
        return null;
      }
      lastSource = 'memory';
      return _map[key];
    }
    await disk.load();
    final row = disk.peek(key);
    if (row == null) {
      lastSource = 'disk_miss';
      return null;
    }
    if (!_rowHasPhones(row.spans)) {
      lastSource = 'disk_no_phones';
      return null;
    }
    lastSource = 'disk';
    _map[key] = row.spoken;
    _spans[key] = row.spans;
    return row.spoken;
  }

  /// Phones for the words of [word] as they sit inside [sentence]. The sentence
  /// already carries them, so a single word never needs its own server call.
  String phonesForWordIn({required String sentence, required String word}) {
    final target = word.trim();
    if (target.isEmpty) return '';
    final at = sentence.indexOf(target);
    if (at < 0) return '';
    final end = at + target.length;
    final out = <String>[];
    for (final span in peekSpans(sentence)) {
      if (span.phone.trim().isEmpty) continue;
      if (span.start < end && span.end > at) out.add(span.phone.trim());
    }
    return out.join(' ');
  }

  List<FollowSpan> peekSpans(String chunk) =>
      _spans[_key(chunk)] ?? const [];

  SpokenAlignMark peekAlign(String chunk) =>
      _align[_key(chunk)] ?? const SpokenAlignMark();

  void put(
    String chunk,
    String spoken, {
    String? version,
    List<FollowSpan> spans = const [],
    SpokenAlignMark align = const SpokenAlignMark(),
  }) {
    if (version != null && version.trim().isNotEmpty) {
      setSpeakNorm(version.trim());
    }
    final key = _key(chunk);
    _map[key] = spoken;
    _spans[key] = spans;
    _align[key] = align;
    unawaited(disk.put(key, spoken, spans));
  }

  void clear() {
    _map.clear();
    _spans.clear();
    _align.clear();
  }
}

int _scoreableSpans(List<FollowSpan> spans) =>
    spans.where((s) => s.weight > 0 && s.end > s.start).length;

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
  bool _phonesWarmed = false;
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

  /// design/383 — load the phoneme model while the first sentence plays.
  Future<void> warmPhonemeModel() async {
    final c = _client;
    if (c == null || !serverEnabled || !cloudSttEnabled) return;
    if (_phonesWarmed) return;
    _phonesWarmed = true;
    await evidence.emit(
      kind: 'practice_skill_spoken',
      cacheId: _cacheId,
      ok: true,
      code: 'phones_warm_start',
      details: {'phase': 'spoken', 'warm_start': 1},
    );
    final sw = Stopwatch()..start();
    var ok = false;
    try {
      ok = await c.warmPhonemeModel();
    } catch (_) {
      ok = false;
    }
    sw.stop();
    await evidence.emit(
      kind: 'practice_skill_spoken',
      cacheId: _cacheId,
      ok: ok,
      code: ok ? 'phones_warm' : 'phones_warm_fail',
      details: {
        'phase': 'spoken',
        'warm_ms': sw.elapsedMilliseconds,
        'warm_ok': ok ? 1 : 0,
      },
    );
  }

  List<String> chunksFor(List<String> base) =>
      effectiveChunks(base, store.state.density);

  Future<String?> ensureSpoken(String chunkDisplay) async {
    final c = _client;
    if (c == null || !serverEnabled) return null;
    final hit = await spokenCache.loadFromDisk(chunkDisplay);
    if (hit != null) {
      final cached = spokenCache.peekAlign(chunkDisplay);
      final cachedSpans = spokenCache.peekSpans(chunkDisplay);
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
          'span_n': cachedSpans.length,
          'pos_span_n': _scoreableSpans(cachedSpans),
          'phone_span_n': spokenCache.phoneSpanN(chunkDisplay),
          'cache_source': spokenCache.lastSource,
          'display_chars': chunkDisplay.length,
          'spoken_chars': hit.length,
          ...cached.details,
        },
      );
      return hit;
    }
    await evidence.emit(
      kind: 'practice_skill_spoken',
      cacheId: _cacheId,
      ok: true,
      code: 'cache_miss',
      details: {
        'phase': 'spoken',
        'cache_hit': 0,
        'cache_source': spokenCache.lastSource,
        'chunk_index': _chunkIndex,
        'display_chars': chunkDisplay.length,
      },
    );
    final sw = Stopwatch()..start();
    try {
      final r = await c.fetchSpokenText(chunkDisplay, cacheId: _cacheId);
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
      spokenCache.put(
        chunkDisplay,
        r.spoken,
        version: r.speakNormVersion,
        spans: r.spans,
        align: SpokenAlignMark(
          code: r.alignCode,
          tokenI: r.alignTokenI,
          cursor: r.alignCursor,
          displayChars: r.alignDisplayChars,
          spokenChars: r.alignSpokenChars,
          tokenLen: r.alignTokenLen,
          pieceLen: r.alignPieceLen,
          differAt: r.alignDifferAt,
          tokenShape: r.alignTokenShape,
          pieceClass: r.alignPieceClass,
          fullClass: r.alignFullClass,
          gapLen: r.alignGapLen,
          gapShape: r.alignGapShape,
          matchedN: r.alignMatchedN,
          tailN: r.alignTailN,
          renamedN: r.alignRenamedN,
          phoneCode: r.phoneCode,
          phoneWordN: r.phoneWordN,
          phoneIpaN: r.phoneIpaN,
          phoneWeightN: r.phoneWeightN,
          phoneFilledN: r.phoneFilledN,
          phoneEspeak: r.phoneEspeak,
          phonePairs: r.phonePairs,
        ),
      );
      final mark = spokenCache.peekAlign(chunkDisplay);
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
          'span_n': r.spans.length,
          'pos_span_n': _scoreableSpans(r.spans),
          'display_chars': chunkDisplay.length,
          'spoken_chars': r.spoken.length,
          ...mark.details,
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
          if (heard != null && heard.trim().isNotEmpty)
            'stt_heard': heard.trim(),
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
    }
    final diag = diagnoseSpokenSlots(
      display: chunkDisplay,
      spoken: spoken,
      spans: spokenCache.peekSpans(chunkDisplay),
      heard: heard,
      heardPhones: (c.lastHeardPhones)
          .split('|')
          .map((part) => part.trim())
          .where((part) => part.isNotEmpty)
          .toList(growable: false),
    );
    final align = spokenCache.peekAlign(chunkDisplay);
    final score = diag.score;
    await evidence.emit(
      kind: 'practice_skill_align',
      cacheId: _cacheId,
      ok: score.ok,
      code: diag.slotCode,
      details: {
        'phase': 'align',
        'slot_code': diag.slotCode,
        'align_code': align.code,
        'span_n': diag.spanN,
        'pos_span_n': diag.posSpanN,
        'slot_n': score.refN,
        'display_chars': chunkDisplay.length,
        'spoken_chars': spoken.length,
        'heard_chars': (heard ?? '').trim().length,
        'walk_i': diag.walkI,
        'piece_weight': diag.pieceWeight,
        'remain': diag.remain,
        'list_v': score.listV,
        'chunk_index': _chunkIndex,
        'spoken_line': spoken,
        'slot_hits': diag.slotHits,
        'slot_pieces': diag.slotPieces,
        'target_phones': spokenCache
            .peekSpans(chunkDisplay)
            .where((span) => span.weight > 0 && span.phone.trim().isNotEmpty)
            .map((span) => span.phone.trim())
            .join(' | '),
        'heard_phones': c.lastHeardPhones,
        ...align.details,
      },
    );
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
        'epoch_n': store.state.epochMeans.length,
        'epoch_target': store.state.epochTargetN,
        'can_finer': canFiner(baseChunks, store.state.density) ? 1 : 0,
        'can_coarser': canCoarser(baseChunks, store.state.density) ? 1 : 0,
        'chunk_index': _chunkIndex,
        'chunk_n': effectiveChunks(baseChunks, store.state.density).length,
        'sentence_id_h16': skillSentenceIdH16(_sentenceId),
        'speak_norm': spokenCache.speakNorm.replaceAll('.', '_'),
        'take_bytes': takeBytes.length,
        'focus_elapsed_ms': _focusElapsedMs,
        'align_code': align.code,
        'tail_n': align.tailN,
        'matched_n': align.matchedN,
        'spoken_line': spoken,
        'slot_hits': diag.slotHits,
        'slot_pieces': diag.slotPieces,
        'target_phones': spokenCache
            .peekSpans(chunkDisplay)
            .where((span) => span.weight > 0 && span.phone.trim().isNotEmpty)
            .map((span) => span.phone.trim())
            .join(' | '),
        'heard_phones': c.lastHeardPhones,
      },
    );
    // design/215 — adapt only on focus-block epoch resolve, not per take.
    return score;
  }

  /// design/364 — speak-window clock. Numbers only, for a short recording.
  Future<void> noteSpeakWindow({
    required int wallMs,
    required int callMs,
    required int playerMs,
    required int padMs,
    required int fileMs,
    required int fileBytes,
    required int audioBytes,
    required int tooShort,
    required String playCode,
  }) async {
    await evidence.emit(
      kind: 'practice_skill_speak_window',
      cacheId: _cacheId,
      ok: tooShort == 0 && playCode == 'played',
      code: tooShort == 1 ? 'too_short' : playCode,
      details: {
        'phase': 'speak_window',
        'wall_ms': wallMs,
        'call_ms': callMs,
        'player_ms': playerMs,
        'pad_ms': padMs,
        'file_ms': fileMs,
        'file_bytes': fileBytes,
        'audio_bytes': audioBytes,
        'too_short': tooShort,
        'play_code': playCode,
        'chunk_index': _chunkIndex,
        'focus_elapsed_ms': _focusElapsedMs,
      },
    );
  }

  /// Wrong-word review. Keeps the expected line, the heard line, and each piece.
  Future<void> noteMissReview({
    required String expected,
    required String? heard,
    required bool matched,
    required String pieces,
    required String hits,
    required int attempt,
    required int wordIndex,
    String drillPhones = '',
    String targetPhones = '',
    String heardPhones = '',
    String drillReason = 'none',
  }) async {
    await evidence.emit(
      kind: 'practice_skill_review',
      cacheId: _cacheId,
      ok: matched,
      code: matched ? 'matched' : 'missed',
      details: {
        'phase': 'review',
        'attempt': attempt,
        'word_index': wordIndex,
        'matched': matched ? 1 : 0,
        'chunk_index': _chunkIndex,
        'spoken_line': expected,
        'slot_pieces': pieces,
        'slot_hits': hits,
        'drill_phone_n': drillPhones.trim().isEmpty
            ? 0
            : drillPhones.trim().split(RegExp(r'\s+')).length,
        'target_phone_n': targetPhones.trim().isEmpty
            ? 0
            : targetPhones.trim().split(RegExp(r'\s+')).length,
        'heard_phone_n': heardPhones.trim().isEmpty
            ? 0
            : heardPhones.trim().split(RegExp(r'\s+')).length,
        'drill_reason': drillReason,
        if (drillPhones.trim().isNotEmpty) 'target_phones': drillPhones.trim(),
        if (heard != null && heard.trim().isNotEmpty) 'stt_heard': heard.trim(),
      },
    );
  }

  Future<void> onFocusBlockDone(List<String> baseChunks) async {
    if (!serverEnabled) return;
    await store.commitFocusBlockMean();
    await store.tickCooldown();

    final decision = decideSkillAdapt(
      state: store.state,
      baseChunks: baseChunks,
    );
    final epochN = store.state.epochMeans.length;
    final epochTarget = store.state.epochTargetN;
    final epochAvg = epochN > 0
        ? store.state.epochMeans.reduce((a, b) => a + b) / epochN
        : null;

    if (decision.reason == 'epoch_wait' || decision.reason == 'cooldown') {
      await evidence.emit(
        kind: 'practice_skill_adapt',
        cacheId: _cacheId,
        ok: true,
        code: decision.reason,
        details: {
          'phase': 'epoch_wait',
          'reason': decision.reason,
          'density_delta': 0,
          'tier_delta': 0,
          'density': store.state.density,
          'tier': store.state.tier,
          'epoch_n': epochN,
          'epoch_target': epochTarget,
          if (epochAvg != null) 'epoch_avg': epochAvg,
          'cooldown': store.state.cooldownBlocks,
        },
      );
      return;
    }

    final apply = resolveSkillAdaptApply(
      state: store.state,
      decision: decision,
    );
    if (apply.changed) {
      await store.setTierDensity(
        tier: apply.tier,
        density: apply.density,
        cooldown: apply.cooldown,
      );
    }
    await store.resolveEpoch(newTargetN: rollSkillEpochTarget());
    await evidence.emit(
      kind: 'practice_skill_adapt',
      cacheId: _cacheId,
      ok: true,
      code: decision.reason,
      details: {
        'phase': 'epoch_adapt',
        'reason': decision.reason,
        'density_delta': decision.densityDelta,
        'tier_delta': decision.tierDelta,
        'density': store.state.density,
        'tier': store.state.tier,
        'density_before': apply.densityBefore,
        'density_after': store.state.density,
        'soft_entry': apply.softEntry ? 1 : 0,
        'epoch_n': epochN,
        'epoch_target': epochTarget,
        if (epochAvg != null) 'epoch_avg': epochAvg,
        'can_finer': canFiner(baseChunks, store.state.density) ? 1 : 0,
        'can_coarser': canCoarser(baseChunks, store.state.density) ? 1 : 0,
      },
    );
  }

  Future<void> flushEvidence({String cacheId = ''}) =>
      evidence.flush(cacheId: cacheId.isEmpty ? _cacheId : cacheId);

  void resetSessionSeq() => evidence.resetSessionSeq();
}
