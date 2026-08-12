/// design/82 — separate shadowing practice mode (mobile).
///
/// Gates: login (shell) · kill · opt-in · chunks built before loop.
/// Loop: listen → record(+2s) → next/skip.
library;

import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';

import '../api/client.dart';
import '../api/reading_models.dart';
import '../api/tts_models.dart';
import '../state/library_controller.dart';
import '../state/shadowing_controller.dart';
import '../state/tts_controller.dart';

class ShadowingPracticeScreen extends StatefulWidget {
  const ShadowingPracticeScreen({
    super.key,
    required this.client,
    required this.library,
    required this.shadowing,
    required this.tts,
  });

  final AsrClient client;
  final LibraryController library;
  final ShadowingController shadowing;
  final TtsController tts;

  @override
  State<ShadowingPracticeScreen> createState() =>
      _ShadowingPracticeScreenState();
}

class _ShadowingPracticeScreenState extends State<ShadowingPracticeScreen> {
  static const _pad = Duration(seconds: 2);
  // WHY: design/82 — Android MediaRecorder via platform channel (no pub `record` dep).
  static const _mic = MethodChannel('asr/shadowing_mic');

  final _player = AudioPlayer();

  String? _status;
  bool _busy = false;
  Map<String, dynamic>? _plan;
  List<String> _chunks = [];
  int _chunkIndex = 0;
  String _sentenceId = '0';
  int _sentenceIndex = 0;

  ReadingSession? get _session => widget.library.session;

  @override
  void dispose() {
    unawaited(_player.dispose());
    unawaited(_mic.invokeMethod<String>('stop'));
    super.dispose();
  }

  @override
  void initState() {
    super.initState();
    unawaited(_boot());
  }

  String get _cacheId {
    final s = _session;
    if (s == null) return '';
    final c = s.cacheId.trim();
    return c.isNotEmpty ? c : s.sessionId;
  }

  Future<void> _boot() async {
    final session = _session;
    if (session == null || !session.isValid) {
      setState(() => _status = '논문을 연 뒤 연습을 시작해 주세요.');
      return;
    }
    if (!widget.shadowing.serverAvailable || !widget.shadowing.enabled) {
      setState(
        () => _status = '설정에서 쉐도잉 연습을 켠 뒤 다시 시도해 주세요.',
      );
      return;
    }
    final cacheId = _cacheId;
    if (cacheId.isEmpty) {
      setState(() => _status = '논문 id가 없습니다.');
      return;
    }
    setState(() {
      _busy = true;
      _status = '연습 구간 준비 중…';
    });
    try {
      // WHY: product B — chunks must succeed before practice room.
      // design/113+119 — pending slices must continue; never treat pending as done.
      var got = await widget.client.fetchShadowingChunks(cacheId);
      var plan = got['plan'];
      if (plan is! Map || plan['status']?.toString() != 'ok') {
        Map<String, dynamic>? built;
        // EDGE: long papers need many budget slices; cap avoids infinite loop.
        const maxRounds = 40;
        for (var round = 0; round < maxRounds; round++) {
          if (!mounted) return;
          setState(() {
            _status = round == 0
                ? '연습 구간 준비 중…'
                : '연습 구간을 이어서 준비하는 중… (${round + 1}/$maxRounds)';
          });
          built = await widget.client.buildShadowingChunks(
            cacheId,
            practiceEnabled: true,
          );
          final p = built['plan'];
          final st = (p is Map) ? p['status']?.toString() : null;
          // Fail-closed: only status=ok enters practice (pending ≠ success).
          if (built['ok'] == true && st == 'ok') {
            plan = p;
            break;
          }
          if (built['continue'] == true && st == 'pending') {
            continue;
          }
          throw AsrApiException(
            built['message']?.toString() ?? '연습 구간을 만들지 못했습니다.',
            502,
          );
        }
        if (plan is! Map || plan['status']?.toString() != 'ok') {
          throw AsrApiException(
            built?['message']?.toString() ??
                '연습 구간 준비가 끝나지 않았습니다. 다시 시도해 주세요.',
            502,
          );
        }
      }
      _plan = Map<String, dynamic>.from(plan as Map);
      _bindSentence(session);
      if (_chunks.isEmpty) {
        throw AsrApiException('이 문장에 연습 구간이 없습니다.', 400);
      }
      await _runCycle();
    } on AsrApiException catch (e) {
      setState(() => _status = e.message);
    } catch (e) {
      setState(() => _status = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _bindSentence(ReadingSession session) {
    _sentenceIndex = session.sentenceIndex;
    final cur = session.currentSentence;
    _sentenceId =
        (cur != null && cur.id.trim().isNotEmpty) ? cur.id : '$_sentenceIndex';
    _chunks = _chunksFor(_sentenceId, cur?.text ?? '');
    _chunkIndex = 0;
  }

  List<String> _chunksFor(String sid, String plain) {
    final sentences = _plan?['sentences'];
    if (sentences is Map && sentences[sid] is Map) {
      final row = sentences[sid] as Map;
      final ch = row['chunks'];
      if (ch is List && ch.isNotEmpty) {
        return ch.map((e) => e.toString()).toList();
      }
    }
    final t = plain.trim();
    return t.isEmpty ? <String>[] : <String>[t];
  }

  Future<void> _playTts(String text) async {
    // design/103 — same mode/voice/rate pick as reader TTS.
    final params = widget.tts.pickPlaybackParams();
    final bytes = await widget.client.synthesizeTts(
      text: text,
      voice: params.voice,
      speakingRate: kTtsRateDefault,
    );
    await _player.stop();
    try {
      await _player.setPlaybackRate(clampSpeakingRate(params.speakingRate));
    } catch (_) {
      // EDGE: player rate unsupported on some devices — still play.
    }
    final done = _player.onPlayerComplete.first;
    await _player.play(BytesSource(Uint8List.fromList(bytes)));
    await done;
  }

  Future<void> _runCycle() async {
    if (_chunks.isEmpty) return;
    setState(() => _status = '듣는 중…');
    await _playTts(_chunks[_chunkIndex]);
    setState(() => _status = '같이 말하는 중… (+2초)');
    var okMic = await _mic.invokeMethod<bool>('hasPermission') ?? false;
    if (!okMic) {
      okMic = await _mic.invokeMethod<bool>('requestPermission') ?? false;
    }
    if (!okMic) {
      setState(() => _status = '마이크 권한이 없습니다. 건너뛰기를 사용할 수 있습니다.');
      return;
    }
    final dir = await getTemporaryDirectory();
    final path =
        '${dir.path}${Platform.pathSeparator}asr_shadow_${DateTime.now().millisecondsSinceEpoch}.m4a';
    final started = await _mic.invokeMethod<bool>('start', {'path': path}) ?? false;
    if (!started) {
      setState(() => _status = '녹음을 시작하지 못했습니다. 건너뛰기를 사용할 수 있습니다.');
      return;
    }
    try {
      await _playTts(_chunks[_chunkIndex]);
      await Future<void>.delayed(_pad);
    } finally {
      final outPath = await _mic.invokeMethod<String>('stop');
      final filePath = (outPath == null || outPath.isEmpty) ? path : outPath;
      final file = File(filePath);
      if (!await file.exists()) {
        setState(() => _status = '녹음 실패. 건너뛰기를 사용할 수 있습니다.');
        return;
      }
      final bytes = await file.readAsBytes();
      if (bytes.isEmpty) {
        setState(() => _status = '녹음이 비었습니다. 건너뛰기를 사용할 수 있습니다.');
        return;
      }
      final cacheId = _cacheId;
      final blobKey =
          'shadowing|$cacheId|$_sentenceId|$_chunkIndex|${DateTime.now().millisecondsSinceEpoch}';
      await widget.client.putVoiceBlob(
        blobKey,
        bytes,
        contentType: 'audio/mp4',
      );
      await widget.client.postShadowingTake(
        cacheId,
        practiceEnabled: true,
        sentenceId: _sentenceId,
        chunkIndex: _chunkIndex,
        chunkCount: _chunks.length,
        status: 'recorded',
        blobKey: blobKey,
        mime: 'audio/mp4',
      );
      setState(() => _status = '저장됨. 「다음」또는「건너뛰기」');
    }
  }

  Future<void> _next({required bool skip}) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final session = _session;
      if (session == null) return;
      final cacheId = _cacheId;
      if (skip) {
        await widget.client.postShadowingTake(
          cacheId,
          practiceEnabled: true,
          sentenceId: _sentenceId,
          chunkIndex: _chunkIndex,
          chunkCount: _chunks.length,
          status: 'skipped',
        );
      }
      if (_chunkIndex + 1 < _chunks.length) {
        _chunkIndex += 1;
      } else if (_sentenceIndex + 1 < session.sentenceCount) {
        await widget.library.advanceSentence(1);
        _bindSentence(session);
        if (_chunks.isEmpty) {
          setState(() => _status = '다음 문장에 연습 구간이 없습니다.');
          return;
        }
      } else {
        setState(() => _status = '이 논문 연습을 끝까지 돌았습니다.');
        return;
      }
      await _runCycle();
    } on AsrApiException catch (e) {
      setState(() => _status = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final prompt = _chunks.isEmpty
        ? ''
        : _chunks[_chunkIndex.clamp(0, _chunks.length - 1)];
    return Scaffold(
      appBar: AppBar(title: const Text('쉐도잉 연습')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              '문장 ${_sentenceIndex + 1} · 구간 ${_chunkIndex + 1}/${_chunks.isEmpty ? 1 : _chunks.length}',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 12),
            Expanded(
              child: SingleChildScrollView(
                child: Text(
                  prompt,
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ),
            ),
            if (_status != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Text(_status!, textAlign: TextAlign.center),
              ),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                FilledButton(
                  onPressed: _busy ? null : () => _next(skip: false),
                  child: const Text('다음'),
                ),
                OutlinedButton(
                  onPressed: _busy ? null : () => _next(skip: true),
                  child: const Text('건너뛰기'),
                ),
              ],
            ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
  }
}
