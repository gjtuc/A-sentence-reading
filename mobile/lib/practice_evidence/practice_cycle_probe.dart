/// design/209 — accumulate one practice cycle into a wide details map.
library;

import 'practice_evidence_encode.dart';

class PracticeCycleProbe {
  PracticeCycleProbe({
    required this.cacheId,
    required this.sentenceId,
    required this.chunkIndex,
    required this.cycleSeq,
    this.schemaV = 1,
    this.baseRate = 1.0,
    this.groomScale = 1.0,
    this.focusElapsedMs = 0,
  });

  final String cacheId;
  final int sentenceId;
  final int chunkIndex;
  final int cycleSeq;
  final int schemaV;
  final double baseRate;
  final double groomScale;
  final int focusElapsedMs;

  final _sw = Stopwatch()..start();
  int listenMs = 0;
  int speakWallMs = 0;
  int padMs = 0;
  int myTakeMs = 0;
  int ttsBytes = 0;
  int ttsOk = 1;
  int voiceHashVal = 0;
  int speakVolPct = 50;
  int listenVolPct = 100;
  int takeOk = 0;
  int takeBytes = 0;
  int takeDurMs = 0;
  int persistOk = 0;
  int cloudTakeOk = 0;
  String micCode = 'none';
  String outcome = 'abandoned';
  String groomSignal = 'none';
  int groomApplied = 0;
  String groomSkip = 'none';
  int groomSessionN = 0;
  int featOk = 0;
  double? bytesRatio;
  double? durRatio;

  void markListen({required int ms, required int bytes, required int voiceHash}) {
    listenMs = ms;
    ttsBytes = bytes;
    voiceHashVal = voiceHash;
  }

  void markTtsFail() {
    ttsOk = 0;
    outcome = 'tts_fail';
  }

  void markSpeak({
    required int wallMs,
    required int padMs,
    required String micCode,
    required bool takeOk,
    required int takeBytes,
    required int takeDurMs,
    required bool persistOk,
    required bool cloudTakeOk,
  }) {
    speakWallMs = wallMs;
    this.padMs = padMs;
    this.micCode = snakeToken(micCode, fallback: 'x');
    this.takeOk = takeOk ? 1 : 0;
    this.takeBytes = takeBytes;
    this.takeDurMs = takeDurMs;
    this.persistOk = persistOk ? 1 : 0;
    this.cloudTakeOk = cloudTakeOk ? 1 : 0;
    if (!takeOk) {
      outcome = 'take_fail';
    }
    if (ttsBytes > 0 && takeBytes > 0) {
      bytesRatio = takeBytes / ttsBytes;
    }
    if (wallMs > 0 && takeDurMs > 0) {
      durRatio = takeDurMs / wallMs;
    }
    // Lightweight stand-in until PCM features (feat_ok stays 0).
    if (bytesRatio != null || durRatio != null) {
      featOk = 0;
    }
  }

  void markMyTake({required int ms}) {
    myTakeMs = ms;
  }

  void markGrooming({
    required String signal,
    required int applied,
    required String skip,
    required int sessionN,
  }) {
    groomSignal = snakeToken(signal, fallback: 'none');
    groomApplied = applied;
    groomSkip = snakeToken(skip.isEmpty ? 'none' : skip, fallback: 'none');
    groomSessionN = sessionN;
  }

  void markComplete() {
    if (outcome == 'tts_fail') return;
    if (takeOk == 1) {
      outcome = 'complete';
      return;
    }
    if (outcome == 'abandoned' && micCode != 'none') {
      outcome = 'take_fail';
    }
  }

  Map<String, Object?> toDetails() {
    final effective = baseRate * groomScale;
    final d = <String, Object?>{
      'schema_v': schemaV,
      'sentence_id': sentenceId,
      'chunk_index': chunkIndex,
      'cycle_seq': cycleSeq,
      'listen_ms': listenMs,
      'speak_wall_ms': speakWallMs,
      'pad_ms': padMs,
      'my_take_ms': myTakeMs,
      'cycle_ms': _sw.elapsedMilliseconds,
      'tts_bytes': ttsBytes,
      'tts_ok': ttsOk,
      'voice_hash': voiceHashVal,
      'base_rate': baseRate,
      'groom_scale': groomScale,
      'effective_rate': effective,
      'speak_vol_pct': speakVolPct,
      'listen_vol_pct': listenVolPct,
      'take_ok': takeOk,
      'take_bytes': takeBytes,
      'take_dur_ms': takeDurMs,
      'persist_ok': persistOk,
      'cloud_take_ok': cloudTakeOk,
      'mic_code': micCode,
      'outcome': snakeToken(outcome, fallback: 'abandoned'),
      'groom_signal': groomSignal,
      'groom_applied': groomApplied,
      'groom_skip': groomSkip,
      'groom_session_n': groomSessionN,
      'focus_elapsed_ms': focusElapsedMs,
      'feat_ok': featOk,
    };
    if (bytesRatio != null) d['bytes_ratio'] = bytesRatio;
    if (durRatio != null) d['dur_ratio'] = durRatio;
    return d;
  }
}
