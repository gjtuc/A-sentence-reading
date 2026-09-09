/// design/82+120+176 — shadowing practice + 10‑min speaking focus clock.
///
/// Gates: login (shell) · kill · opt-in · chunks built before loop.
/// Loop per chunk: listen TTS → speak+TTS(reuse bytes) → my-take replay → next.
/// Focus clock only during speak (mic open). Manual next/retry/replay removed.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';
import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';

import '../api/client.dart';
import '../api/focus_practice_models.dart';
import '../api/reading_models.dart';
import '../api/shadowing_chunk_plan.dart';
import '../api/tts_models.dart';
import '../services/evidence_bus.dart';
import '../services/shadowing_disk_store.dart';
import '../services/shadowing_cloud_migrate.dart';
import '../state/focus_practice_controller.dart';
import '../state/library_controller.dart';
import '../state/practice_bookmark_controller.dart';
import '../state/shadowing_controller.dart';
import '../state/tts_controller.dart';
import '../widgets/focus_practice_calendar_sheet.dart';
import '../widgets/practice_mirror_panel.dart';
import '../widgets/reader_nav_picker.dart';


class ShadowingPracticeScreen extends StatefulWidget {
  const ShadowingPracticeScreen({
    super.key,
    required this.client,
    required this.library,
    required this.shadowing,
    required this.tts,
    this.focus,
  });

  final AsrClient client;
  final LibraryController library;
  final ShadowingController shadowing;
  final TtsController tts;
  final FocusPracticeController? focus;

  @override
  State<ShadowingPracticeScreen> createState() =>
      _ShadowingPracticeScreenState();
}

class _ShadowingPracticeScreenState extends State<ShadowingPracticeScreen>
    with WidgetsBindingObserver {
  static const _pad = Duration(seconds: 2);
  // WHY: design/82 — Android MediaRecorder via platform channel (no pub `record` dep).
  static const _mic = MethodChannel('asr/shadowing_mic');

  final _player = AudioPlayer();
  late final FocusPracticeController _focus;
  late final bool _ownsFocus;
  final ShadowingDiskStore _disk = ShadowingDiskStore();
  final PracticeBookmarkController _practiceBookmarks =
      PracticeBookmarkController();

  String? _status;
  bool _busy = false;
  /// Prep/boot failed — show 「다시 시도」 (not a dead-end status string).
  bool _bootFailed = false;
  /// Plan bound and at least one playable chunk — unlock loop chrome / mirror.
  bool _practiceReady = false;
  Map<String, dynamic>? _plan;
  Map<String, dynamic>? _takes;
  List<String> _chunks = [];
  int _chunkIndex = 0;
  String _sentenceId = '0';
  int _sentenceIndex = 0;
  /// design/120 — last local take path for replay phase (this chunk).
  String? _lastTakePath;
  /// Per-chunk TTS: one random voice/rate draw; bytes reused for listen+speak.
  Uint8List? _chunkTtsBytes;
  TtsPlaybackParams? _chunkTtsParams;
  /// design/162 — session-only self-view mirror (not persisted).
  bool _mirrorEnabled = false;
  /// design/176 — auto-advance after full listen→speak→my-take cycle.
  final bool _autoAdvance = true;
  /// Invalidate in-flight cycle on give-up / picker jump.
  int _cycleToken = 0;

  ReadingSession? get _session => widget.library.session;

  bool get _localSot => widget.shadowing.localSot;

  String _shadowingMigratedPrefsKey() {
    final u = (widget.shadowing.boundUid ?? '')
        .trim()
        .replaceAll(RegExp(r'[^A-Za-z0-9_\-]'), '');
    if (u.isEmpty) return 'asr.shadowing.cloud_migrated.v1';
    final safe = u.length > 128 ? u.substring(0, 128) : u;
    return 'asr.shadowing.cloud_migrated.v1.u.$safe';
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _ownsFocus = widget.focus == null;
    _focus = widget.focus ?? FocusPracticeController();
    _focus.addListener(_onFocusTick);
    _practiceBookmarks.addListener(_onPracticeBookmarksTick);
    unawaited(_boot());
  }

  void _onFocusTick() {
    if (mounted) setState(() {});
  }

  void _onPracticeBookmarksTick() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    widget.library.removeListener(_onLibraryPrepTick);
    _practiceBookmarks.removeListener(_onPracticeBookmarksTick);
    _focus.removeListener(_onFocusTick);
    if (_focus.speaking) {
      _focus.endSpeak(cacheId: _cacheId);
    }
    if (_ownsFocus) {
      _focus.dispose();
    }
    _practiceBookmarks.dispose();
    unawaited(_player.dispose());
    unawaited(_mic.invokeMethod<String>('stop'));
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.inactive ||
        state == AppLifecycleState.paused) {
      _focus.onAppPaused(cacheId: _cacheId);
    }
  }

  String get _cacheId {
    final s = _session;
    if (s == null) return '';
    final c = s.cacheId.trim();
    return c.isNotEmpty ? c : s.sessionId;
  }

  String _sidH16(String sid) {
    final t = sid.trim();
    if (t.isEmpty) return '';
    return sha256.convert(utf8.encode(t)).toString().substring(0, 16);
  }

  String _prepStatusLine() {
    final prog = widget.library.shadowingChunksProgress;
    if (prog != null && prog.trim().isNotEmpty) {
      return '연습 구간 준비 중 · $prog';
    }
    return '연습 구간 준비 중…';
  }

  void _onLibraryPrepTick() {
    if (!mounted || !_busy || _practiceReady) return;
    setState(() => _status = _prepStatusLine());
  }

  Future<void> _boot() async {
    await _focus.bindUid(widget.shadowing.boundUid);
    _disk.bindUid(widget.shadowing.boundUid);
    await _practiceBookmarks.bindUid(widget.shadowing.boundUid);
    final session = _session;
    if (session == null || !session.isValid) {
      asrEvidenceBus?.record(
        'shadowing_gate',
        severity: 'decision',
        ok: false,
        code: 'no_session',
        details: {
          'gate': 'no_session',
          'server_flag': widget.shadowing.serverAvailable,
          'pref': widget.shadowing.enabled,
        },
      );
      setState(() {
        _bootFailed = true;
        _practiceReady = false;
        _status = '논문을 연 뒤 연습을 시작해 주세요.';
      });
      return;
    }
    if (!widget.shadowing.serverAvailable || !widget.shadowing.enabled) {
      final gate =
          !widget.shadowing.serverAvailable ? 'kill_off' : 'pref_off';
      asrEvidenceBus?.record(
        'shadowing_gate',
        severity: 'decision',
        ok: false,
        code: gate,
        details: {
          'gate': gate,
          'server_flag': widget.shadowing.serverAvailable,
          'pref': widget.shadowing.enabled,
        },
      );
      setState(() {
        _bootFailed = true;
        _practiceReady = false;
        _status = '설정에서 쉐도잉 연습을 켠 뒤 다시 시도해 주세요.';
      });
      return;
    }
    final cacheId = _cacheId;
    if (cacheId.isEmpty) {
      asrEvidenceBus?.record(
        'shadowing_gate',
        severity: 'decision',
        ok: false,
        code: 'no_cache_id',
        details: {
          'gate': 'no_cache_id',
          'server_flag': true,
          'pref': true,
        },
      );
      setState(() {
        _bootFailed = true;
        _practiceReady = false;
        _status = '논문 id가 없습니다.';
      });
      return;
    }
    setState(() {
      _busy = true;
      _bootFailed = false;
      _practiceReady = false;
      _status = _prepStatusLine();
    });
    await _practiceBookmarks.loadPaper(cacheId);
    final sw = Stopwatch()..start();
    asrEvidenceBus?.record(
      'shadowing_boot_start',
      cacheId: cacheId,
      severity: 'lifecycle',
    );
    var rounds = 0;
    var planStatus = '';
    var errorCode = '';
    var chunkN = 0;
    var skippedEmptyN = 0;
    widget.library.addListener(_onLibraryPrepTick);
    try {
      if (_localSot) {
        await _migrateShadowingOnce(cacheId);
      }
      final localTakes = await _disk.loadTakesJson(cacheId);
      if (localTakes != null) {
        _takes = localTakes;
      }

      // Prefer local ok plan (device SoT) before network / ensure.
      Map<String, dynamic>? plan = await _disk.loadChunkPlanJson(cacheId);
      if (plan == null || plan['status']?.toString() != 'ok') {
        try {
          final got = await widget.client.fetchShadowingChunks(cacheId);
          final p = got['plan'];
          if (p is Map && p['status']?.toString() == 'ok') {
            plan = Map<String, dynamic>.from(p);
          }
        } catch (_) {
          // Fall through to library ensure.
        }
      }

      // Single prep path: join LibraryController ensure (progress + 40-slice).
      if (plan == null || plan['status']?.toString() != 'ok') {
        if (!mounted) return;
        setState(() => _status = _prepStatusLine());
        await widget.library.ensureShadowingChunks(
          cacheId,
          trigger: 'practice_boot',
        );
        rounds = 1;
        plan = await _disk.loadChunkPlanJson(cacheId);
        if (plan == null || plan['status']?.toString() != 'ok') {
          try {
            final got = await widget.client.fetchShadowingChunks(cacheId);
            final p = got['plan'];
            if (p is Map && p['status']?.toString() == 'ok') {
              plan = Map<String, dynamic>.from(p);
            }
          } catch (_) {}
        }
        if (plan == null || plan['status']?.toString() != 'ok') {
          final err = widget.library.shadowingChunksError;
          errorCode = (err != null && err.contains('끝나지 않았'))
              ? 'cap_hit'
              : 'build_failed';
          throw AsrApiException(
            (err != null && err.trim().isNotEmpty)
                ? err
                : '연습 구간 준비가 끝나지 않았습니다. 다시 시도해 주세요.',
            502,
          );
        }
      }
      planStatus = 'ok';
      _plan = Map<String, dynamic>.from(plan);
      unawaited(_disk.writeChunkPlanJson(cacheId, _plan!));

      skippedEmptyN = await _skipToPlayableSentence(session);
      chunkN = _chunks.length;
      if (_chunks.isEmpty) {
        errorCode = 'chunk_empty';
        throw AsrApiException('이 논문에 연습할 구간이 없습니다.', 400);
      }
      asrEvidenceBus?.record(
        'shadowing_boot_done',
        cacheId: cacheId,
        severity: 'lifecycle',
        ok: true,
        details: {
          'plan_status': planStatus,
          'rounds': rounds,
          'chunk_n': chunkN,
          'sentence_id_h16': _sidH16(_sentenceId),
          'elapsed_ms': sw.elapsedMilliseconds,
          'skipped_empty_n': skippedEmptyN,
        },
      );
      if (mounted) {
        setState(() {
          _practiceReady = true;
          _bootFailed = false;
        });
      }
      _focus.startSession(cacheId: cacheId);
      await _runCycle();
    } on AsrApiException catch (e) {
      asrEvidenceBus?.record(
        'shadowing_boot_done',
        cacheId: cacheId,
        severity: 'lifecycle',
        ok: false,
        code: errorCode.isNotEmpty ? errorCode : 'api_fail',
        details: {
          'plan_status': planStatus,
          'rounds': rounds,
          'chunk_n': chunkN,
          'sentence_id_h16': _sidH16(_sentenceId),
          'elapsed_ms': sw.elapsedMilliseconds,
          'error_code': errorCode.isNotEmpty ? errorCode : 'api_fail',
          'skipped_empty_n': skippedEmptyN,
        },
      );
      setState(() {
        _bootFailed = true;
        _practiceReady = false;
        _status = e.message;
      });
    } catch (e) {
      asrEvidenceBus?.record(
        'shadowing_boot_done',
        cacheId: cacheId,
        severity: 'lifecycle',
        ok: false,
        code: 'boot_error',
        details: {
          'plan_status': planStatus,
          'rounds': rounds,
          'chunk_n': chunkN,
          'sentence_id_h16': _sidH16(_sentenceId),
          'elapsed_ms': sw.elapsedMilliseconds,
          'error_code': 'boot_error',
          'skipped_empty_n': skippedEmptyN,
        },
      );
      setState(() {
        _bootFailed = true;
        _practiceReady = false;
        _status = e.toString();
      });
    } finally {
      widget.library.removeListener(_onLibraryPrepTick);
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _handlePracticeBookmarkTap() async {
    final session = _session;
    if (session == null || session.sentenceCount == 0) return;
    if (!_practiceBookmarks.canBookmark) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('연습 북마크를 쓰려면 로그인해 주세요.')),
      );
      return;
    }
    final nav = session.sectionNav;
    final key = nav.sentenceBookmarkKeyForGlobal(session.sentenceIndex);
    if (_practiceBookmarks.isSentenceBookmarked(key)) {
      await _practiceBookmarks.toggleSentenceBookmark(
        nav,
        session.sentenceIndex,
      );
      return;
    }
    final header = nav.headerPartsFor(session.sentenceIndex);
    final label = header.sectionName.isEmpty
        ? '${header.position}번 문장'
        : '${header.sectionName} ${header.position}번';
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('연습 북마크할까요?'),
        content: Text(
          '$label을 연습 북마크하면 연습 화면에서만 쉽게 찾을 수 있어요. 읽기 북마크와는 별개입니다.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('아니오'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('예'),
          ),
        ],
      ),
    );
    if (ok == true) {
      await _practiceBookmarks.toggleSentenceBookmark(
        nav,
        session.sentenceIndex,
      );
    }
  }

  Future<void> _openPracticeSentencePicker() async {
    final session = _session;
    if (session == null || session.sentenceCount == 0) return;
    final nav = session.sectionNav;
    if (nav.sectionCount < 1) return;
    final hints = BookmarkPickerHints(
      leftBadgeCount: (i) =>
          _practiceBookmarks.pickerSectionBadgeCount(nav, i),
      rightHighlighted: (left, right) =>
          _practiceBookmarks.pickerSentenceHighlighted(nav, left, right),
    );
    final idx = await showSectionNavPicker(
      context: context,
      nav: nav,
      currentGlobalIndex: session.sentenceIndex,
      bookmarks: hints,
    );
    if (idx == null || !mounted) return;
    await _goToPracticeSentence(idx);
  }

  /// Advance reader past empty sentences until chunks exist (or end).
  /// Returns how many sentences were skipped.
  Future<int> _skipToPlayableSentence(ReadingSession session) async {
    final rows = <({String id, String text})>[
      for (final s in session.sentences) (id: s.id, text: s.text),
    ];
    final delta = shadowingSkipEmptyDelta(
      plan: _plan,
      sentences: rows,
      fromIndex: session.sentenceIndex,
    );
    if (delta < 0) {
      _bindSentence(session);
      return 0;
    }
    if (delta > 0) {
      await widget.library.advanceSentence(delta);
    }
    _bindSentence(session);
    return delta;
  }

  /// design/187 — one-shot pull takes + voice blobs, then ack wipe.
  Future<void> _migrateShadowingOnce(String cacheId) async {
    final ok = await migrateShadowingCloudOnce(
      client: widget.client,
      uid: widget.shadowing.boundUid,
      cacheIds: [cacheId],
      disk: _disk,
    );
    if (!ok) return;
    final local = await _disk.loadTakesJson(cacheId);
    if (local != null) _takes = local;
  }

  Future<void> _persistTakeLocal({
    required String cacheId,
    required String status,
    String? blobKey,
    String? mime,
    List<int>? voiceBytes,
  }) async {
    if (blobKey != null && voiceBytes != null && voiceBytes.isNotEmpty) {
      await _disk.writeVoiceBytes(cacheId, blobKey, voiceBytes);
    }
    final takes = Map<String, dynamic>.from(
      _takes ??
          {
            'version': 1,
            'cache_id': cacheId,
            'sentences': <String, dynamic>{},
          },
    );
    final sentences = Map<String, dynamic>.from(
      (takes['sentences'] is Map)
          ? Map<String, dynamic>.from(takes['sentences'] as Map)
          : <String, dynamic>{},
    );
    final row = Map<String, dynamic>.from(
      (sentences[_sentenceId] is Map)
          ? Map<String, dynamic>.from(sentences[_sentenceId] as Map)
          : <String, dynamic>{},
    );
    final chunks = List<dynamic>.from(
      (row['chunks'] is List) ? row['chunks'] as List : const [],
    );
    while (chunks.length <= _chunkIndex) {
      chunks.add({'status': 'empty', 'blob_key': null, 'mime': null});
    }
    chunks[_chunkIndex] = {
      'status': status,
      'blob_key': blobKey,
      'mime': mime,
    };
    row['chunks'] = chunks;
    sentences[_sentenceId] = row;
    takes['sentences'] = sentences;
    takes['cache_id'] = cacheId;
    _takes = takes;
    await _disk.writeTakesJson(cacheId, takes);
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
    return shadowingChunksForSentence(_plan, sid, plain);
  }

  void _clearChunkTtsCache() {
    _chunkTtsBytes = null;
    _chunkTtsParams = null;
  }

  Future<void> _ensureChunkTts(String text) async {
    if (_chunkTtsBytes != null && _chunkTtsParams != null) return;
    final params = widget.tts.pickPlaybackParams();
    final bytes = await widget.client.synthesizeTts(
      text: text,
      voice: params.voice,
      speakingRate: kTtsRateDefault,
    );
    _chunkTtsBytes = Uint8List.fromList(bytes);
    _chunkTtsParams = params;
  }

  Future<void> _playCachedChunkTts({required String phase}) async {
    final text = _chunks[_chunkIndex];
    try {
      await _ensureChunkTts(text);
      final bytes = _chunkTtsBytes!;
      final params = _chunkTtsParams!;
      await _player.stop();
      try {
        await _player.setPlaybackRate(clampSpeakingRate(params.speakingRate));
      } catch (_) {
        // EDGE: player rate unsupported on some devices — still play.
      }
      final done = _player.onPlayerComplete.first;
      await _player.play(BytesSource(bytes));
      await done;
      asrEvidenceBus?.record(
        'shadowing_loop_event',
        cacheId: _cacheId,
        ok: true,
        details: {
          'phase': phase,
          'ok': true,
          'tts_reuse': phase == 'tts_speak' ? 1 : 0,
        },
      );
    } catch (e) {
      asrEvidenceBus?.record(
        'shadowing_loop_event',
        cacheId: _cacheId,
        ok: false,
        code: 'tts_fail',
        details: {
          'phase': phase,
          'ok': false,
          'exc_type': e.runtimeType.toString(),
        },
      );
      rethrow;
    }
  }

  /// listen TTS → speak+TTS(reuse) → my take replay → next chunk.
  Future<void> _runCycle() async {
    if (_chunks.isEmpty) return;
    if (!_focus.sessionActive || _focus.paused) return;
    final token = ++_cycleToken;
    // Continuous loop must not pin _busy (bookmark / calendar stay usable).
    if (mounted && _busy) setState(() => _busy = false);
    _clearChunkTtsCache();
    _lastTakePath = null;

    bool alive() =>
        mounted &&
        token == _cycleToken &&
        _focus.sessionActive &&
        !_focus.paused;

    setState(() => _status = '듣는 중');
    await _playCachedChunkTts(phase: 'tts_listen');
    if (!alive()) return;

    final takeOk = await _runSpeakPhase();
    if (!alive()) return;
    if (!takeOk) {
      await Future<void>.delayed(const Duration(milliseconds: 800));
      if (!alive()) return;
      await _advanceToNextChunk(token: token);
      return;
    }

    await _playMyTakePhase();
    if (!alive()) return;

    if (_autoAdvance) {
      await _advanceToNextChunk(token: token);
    }
  }

  /// Phase 2 — mic open; focus clock runs only here. Reuses chunk TTS bytes.
  Future<bool> _runSpeakPhase() async {
    if (_chunks.isEmpty) return false;
    setState(() => _status = '말하는 중');
    var okMic = await _mic.invokeMethod<bool>('hasPermission') ?? false;
    if (!okMic) {
      okMic = await _mic.invokeMethod<bool>('requestPermission') ?? false;
    }
    if (!okMic) {
      asrEvidenceBus?.record(
        'shadowing_loop_event',
        cacheId: _cacheId,
        ok: false,
        code: 'mic_perm',
        details: {'phase': 'mic_start', 'ok': false, 'exc_type': 'mic_perm'},
      );
      setState(() => _status = '마이크 권한이 없습니다. 다음 구간으로 넘어갑니다.');
      return false;
    }
    final dir = await getTemporaryDirectory();
    final path =
        '${dir.path}${Platform.pathSeparator}asr_shadow_${DateTime.now().millisecondsSinceEpoch}.m4a';
    final started =
        await _mic.invokeMethod<bool>('start', {'path': path}) ?? false;
    if (!started) {
      asrEvidenceBus?.record(
        'shadowing_loop_event',
        cacheId: _cacheId,
        ok: false,
        code: 'mic_start',
        details: {'phase': 'mic_start', 'ok': false, 'exc_type': 'mic_start'},
      );
      setState(() => _status = '녹음을 시작하지 못했습니다. 다음 구간으로 넘어갑니다.');
      return false;
    }
    _focus.beginSpeak();
    asrEvidenceBus?.record(
      'shadowing_loop_event',
      cacheId: _cacheId,
      ok: true,
      details: {'phase': 'mic_start', 'ok': true},
    );
    var takeOk = false;
    try {
      await _playCachedChunkTts(phase: 'tts_speak');
      await Future<void>.delayed(_pad);
    } finally {
      _focus.endSpeak(cacheId: _cacheId);
      final outPath = await _mic.invokeMethod<String>('stop');
      asrEvidenceBus?.record(
        'shadowing_loop_event',
        cacheId: _cacheId,
        ok: true,
        details: {'phase': 'mic_stop', 'ok': true},
      );
      final filePath = (outPath == null || outPath.isEmpty) ? path : outPath;
      final file = File(filePath);
      if (!await file.exists()) {
        setState(() => _status = '녹음 실패. 다음 구간으로 넘어갑니다.');
      } else {
        final bytes = await file.readAsBytes();
        if (bytes.isEmpty) {
          setState(() => _status = '녹음이 비었습니다. 다음 구간으로 넘어갑니다.');
        } else {
          _lastTakePath = filePath;
          final cacheId = _cacheId;
          final blobKey =
              'shadowing|$cacheId|$_sentenceId|$_chunkIndex|${DateTime.now().millisecondsSinceEpoch}';
          try {
            await _persistTakeLocal(
              cacheId: cacheId,
              status: 'recorded',
              blobKey: blobKey,
              mime: 'audio/mp4',
              voiceBytes: bytes,
            );
            if (!_localSot) {
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
            }
            asrEvidenceBus?.record(
              'shadowing_loop_event',
              cacheId: cacheId,
              ok: true,
              details: {
                'phase': 'take_post',
                'ok': true,
                'local_sot': _localSot,
              },
            );
            takeOk = true;
            setState(() => _status = '저장됨');
          } on AsrApiException catch (e) {
            if (e.statusCode == 409) {
              takeOk = true;
              setState(() => _status = '저장됨');
            } else {
              asrEvidenceBus?.record(
                'shadowing_loop_event',
                cacheId: cacheId,
                ok: false,
                code: 'take_post',
                details: {
                  'phase': 'take_post',
                  'ok': false,
                  'exc_type': e.runtimeType.toString(),
                },
              );
              rethrow;
            }
          } catch (e) {
            asrEvidenceBus?.record(
              'shadowing_loop_event',
              cacheId: cacheId,
              ok: false,
              code: 'take_post',
              details: {
                'phase': 'take_post',
                'ok': false,
                'exc_type': e.runtimeType.toString(),
              },
            );
            rethrow;
          }
        }
      }
    }
    return takeOk;
  }

  /// Phase 3 — my recording only; focus clock must stay off.
  Future<void> _playMyTakePhase() async {
    final path = (_lastTakePath ?? '').trim();
    if (path.isEmpty) return;
    final file = File(path);
    if (!await file.exists()) return;
    setState(() => _status = '내 녹음 듣는 중');
    try {
      await _player.stop();
      final done = _player.onPlayerComplete.first;
      await _player.play(DeviceFileSource(path));
      await done;
      asrEvidenceBus?.record(
        'shadowing_loop_event',
        cacheId: _cacheId,
        ok: true,
        details: {'phase': 'my_take_replay', 'ok': true},
      );
      if (mounted) setState(() => _status = '저장됨');
    } catch (e) {
      asrEvidenceBus?.record(
        'shadowing_loop_event',
        cacheId: _cacheId,
        ok: false,
        code: 'replay_fail',
        details: {
          'phase': 'my_take_replay',
          'ok': false,
          'exc_type': e.runtimeType.toString(),
        },
      );
      if (mounted) setState(() => _status = '녹음 재생에 실패했습니다.');
    }
  }

  Future<void> _advanceToNextChunk({required int token}) async {
    if (!mounted || token != _cycleToken) return;
    final session = _session;
    if (session == null) return;
    _lastTakePath = null;
    _clearChunkTtsCache();
    if (_chunkIndex + 1 < _chunks.length) {
      _chunkIndex += 1;
    } else if (_sentenceIndex + 1 < session.sentenceCount) {
      final rows = <({String id, String text})>[
        for (final s in session.sentences) (id: s.id, text: s.text),
      ];
      final delta = shadowingSkipEmptyDelta(
        plan: _plan,
        sentences: rows,
        fromIndex: _sentenceIndex + 1,
      );
      if (delta < 0) {
        setState(() => _status = '이 논문 연습을 끝까지 돌았습니다.');
        return;
      }
      await widget.library.advanceSentence(1 + delta);
      _bindSentence(session);
      if (_chunks.isEmpty) {
        setState(() => _status = '이 논문 연습을 끝까지 돌았습니다.');
        return;
      }
    } else {
      setState(() => _status = '이 논문 연습을 끝까지 돌았습니다.');
      return;
    }
    if (!mounted || token != _cycleToken) return;
    await _runCycle();
  }

  void _toggleMirror() {
    setState(() => _mirrorEnabled = !_mirrorEnabled);
  }

  void _onGiveUp() {
    _cycleToken++;
    unawaited(_player.stop());
    unawaited(_mic.invokeMethod<String>('stop'));
    if (_focus.speaking) {
      _focus.endSpeak(cacheId: _cacheId);
    }
    _focus.giveUp(cacheId: _cacheId);
    _clearChunkTtsCache();
    setState(
      () => _status =
          '집중 종료 · 미완료 10분은 초기화됩니다. 「시작」으로 다시.',
    );
  }

  void _openFocusCalendar() {
    unawaited(
      showFocusPracticeCalendarSheet(context: context, focus: _focus),
    );
  }

  Future<void> _onRetryBoot() async {
    if (_busy) return;
    await _boot();
  }

  void _onRestartFocus() {
    _focus.startSession(cacheId: _cacheId);
    setState(() => _status = '집중 시작. 말할 때만 시계가 갑니다.');
    if (!_busy && _chunks.isNotEmpty) {
      unawaited(_runCycle());
    }
  }

  Future<void> _goToPracticeSentence(int globalIndex) async {
    _cycleToken++;
    unawaited(_player.stop());
    try {
      await _mic.invokeMethod<String>('stop');
    } catch (_) {}
    if (_focus.speaking) {
      _focus.endSpeak(cacheId: _cacheId);
    }
    _clearChunkTtsCache();
    _lastTakePath = null;
    if (_busy) return;
    setState(() => _busy = true);
    try {
      await widget.library.goToSentenceIndex(globalIndex);
      final session = _session;
      if (session == null) return;
      _bindSentence(session);
      if (_chunks.isEmpty) {
        setState(() => _status = '이 문장에 연습 구간이 없습니다.');
        return;
      }
      if (!_focus.sessionActive) {
        _focus.startSession(cacheId: _cacheId);
      }
      setState(() => _busy = false);
      await _runCycle();
    } on AsrApiException catch (e) {
      if (mounted) setState(() => _status = e.message);
    } catch (e) {
      if (mounted) setState(() => _status = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final prompt = _chunks.isEmpty
        ? ''
        : _chunks[_chunkIndex.clamp(0, _chunks.length - 1)];
    final theme = Theme.of(context);
    final remaining = _focus.displayRemaining;
    final elapsed = _focus.displayElapsed;
    final blockLabel = formatFocusClock(
      // Tomato-like: show time spent speaking in this block (counts up).
      elapsed,
    );
    final missionLeft = formatFocusClock(remaining);

    final showMirror = _practiceReady && _mirrorEnabled;

    return Scaffold(
      backgroundColor: const Color(0xFF1A1A1A),
      appBar: AppBar(
        backgroundColor: const Color(0xFF1A1A1A),
        foregroundColor: Colors.white,
        title: const Text('따라 말하기'),
        actions: [
          IconButton(
            icon: const Icon(Icons.calendar_month_outlined, color: Colors.white70),
            tooltip: '연습 캘린더',
            onPressed: _openFocusCalendar,
          ),
          if (_practiceReady)
            IconButton(
              icon: Icon(
                _mirrorEnabled ? Icons.videocam : Icons.videocam_off_outlined,
                color: Colors.white70,
              ),
              tooltip: _mirrorEnabled ? '카메라 끄기' : '카메라 켜기',
              onPressed: _busy ? null : _toggleMirror,
            ),
        ],
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (!_practiceReady)
                Text(
                  '연습 준비',
                  textAlign: TextAlign.center,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: Colors.white54,
                  ),
                )
              else ...[
                Builder(
                  builder: (context) {
                    final session = _session;
                    if (session == null || session.sentenceCount == 0) {
                      return Text(
                        '문장 없음',
                        textAlign: TextAlign.center,
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: Colors.white54,
                        ),
                      );
                    }
                    final nav = session.sectionNav;
                    final header = nav.headerPartsFor(session.sentenceIndex);
                    final sentKey =
                        nav.sentenceBookmarkKeyForGlobal(session.sentenceIndex);
                    final highlighted =
                        _practiceBookmarks.isSentenceBookmarked(sentKey);
                    final sectionBadge = _practiceBookmarks.sectionBadgeCount(
                      nav,
                      session.sentenceIndex,
                    );
                    final canPick = nav.sectionCount > 0;
                    return Column(
                      children: [
                        Theme(
                          data: Theme.of(context).copyWith(
                            textTheme: Theme.of(context).textTheme.apply(
                                  bodyColor: Colors.white70,
                                  displayColor: Colors.white70,
                                ),
                          ),
                          child: ReaderNavHeaderLabel(
                            left: header.sectionName.isEmpty
                                ? 'Sentence'
                                : header.sectionName,
                            right: header.rightLabel,
                            enabled: !_busy,
                            highlighted: highlighted,
                            leftBadgeCount: sectionBadge,
                            onTap: _busy ? null : _handlePracticeBookmarkTap,
                            onLongPress: (_busy || !canPick)
                                ? null
                                : _openPracticeSentencePicker,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          '구간 ${_chunkIndex + 1}/${_chunks.isEmpty ? 1 : _chunks.length}',
                          textAlign: TextAlign.center,
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: Colors.white38,
                          ),
                        ),
                      ],
                    );
                  },
                ),
              ],
              if (showMirror) ...[
                const SizedBox(height: 8),
                SizedBox(
                  height: MediaQuery.sizeOf(context).height * 0.18,
                  child: const PracticeMirrorPanel(),
                ),
              ],
              const SizedBox(height: 12),
              // Sentence ABOVE timer (design/176).
              Expanded(
                flex: 3,
                child: Center(
                  child: SingleChildScrollView(
                    child: Text(
                      prompt.isEmpty ? '…' : prompt,
                      textAlign: TextAlign.center,
                      style: theme.textTheme.headlineSmall?.copyWith(
                        color: Colors.white,
                        height: 1.35,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 8),
              Text(
                blockLabel,
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontFamily: 'monospace',
                  fontSize: 56,
                  fontWeight: FontWeight.w300,
                  color: Colors.white,
                  letterSpacing: 2,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                _focus.daySuccess
                    ? '오늘 성공 · ${_focus.blocksCompletedToday}블록 · 다음까지 $missionLeft'
                    : '10분 말하기 · 남은 $missionLeft',
                textAlign: TextAlign.center,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: _focus.daySuccess
                      ? const Color(0xFF7DCEA0)
                      : Colors.white70,
                ),
              ),
              if (_status != null) ...[
                const SizedBox(height: 8),
                Text(
                  _status!,
                  textAlign: TextAlign.center,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: _bootFailed
                        ? const Color(0xFFE74C3C)
                        : Colors.white54,
                  ),
                ),
              ],
              const SizedBox(height: 16),
              if (_bootFailed)
                SizedBox(
                  height: 48,
                  child: FilledButton(
                    style: FilledButton.styleFrom(
                      backgroundColor: const Color(0xFFE74C3C),
                      foregroundColor: Colors.white,
                    ),
                    onPressed: _busy ? null : _onRetryBoot,
                    child: const Text('다시 시도'),
                  ),
                )
              else if (_focus.sessionActive)
                SizedBox(
                  height: 48,
                  child: OutlinedButton(
                    style: OutlinedButton.styleFrom(
                      foregroundColor: Colors.white70,
                      side: const BorderSide(color: Colors.white38),
                    ),
                    onPressed: _onGiveUp,
                    child: const Text('집중 끝내기'),
                  ),
                )
              else if (_practiceReady)
                SizedBox(
                  height: 48,
                  child: FilledButton(
                    style: FilledButton.styleFrom(
                      backgroundColor: const Color(0xFFE74C3C),
                      foregroundColor: Colors.white,
                    ),
                    onPressed: _busy ? null : _onRestartFocus,
                    child: const Text('시작'),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
