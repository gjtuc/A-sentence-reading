/// design/82+120+176+214+245 — shadowing practice + minimal rhythm + judgment cheers.
///
/// Gates: login (shell) · kill · opt-in · chunks built before loop.
/// Loop per chunk: listen TTS → speak+TTS(reuse bytes) → my-take replay → next.
/// Focus clock only during speak after mic ready-beat (design/245). Manual next/retry/replay removed.
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
import 'package:shared_preferences/shared_preferences.dart';

import '../api/cite_refs.dart' as cite;
import '../api/client.dart';
import '../api/focus_practice_models.dart';
import '../api/practice_progress_store.dart';
import '../api/reading_models.dart';
import '../api/shadowing_chunk_plan.dart';
import '../api/tts_models.dart';
import '../practice_grooming/grooming_policy.dart';
import '../practice_grooming/practice_grooming_controller.dart';
import '../practice_rhythm/judgment_burst.dart';
import '../practice_rhythm/judgment_copy.dart';
import '../practice_rhythm/judgment_prefs.dart';
import '../practice_rhythm/judgment_tier.dart';
import '../practice_rhythm/phase_rail.dart';
import '../practice_rhythm/rhythm_theme.dart';
import '../practice_skill/chunk_density.dart';
import '../practice_skill/practice_skill_controller.dart';
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
  /// design/245 — after mic start, brief beat before speak-guide TTS / user speech.
  static const _speakMicReadyBeat = Duration(milliseconds: 350);
  // WHY: design/82 — Android MediaRecorder via platform channel (no pub `record` dep).
  static const _mic = MethodChannel('asr/shadowing_mic');
  /// Speak phase only — quieter guide so mic take keeps user voice (design/206+215).
  static const double _kSpeakTtsVolume = 0.2;
  static const double _kFullTtsVolume = 1.0;

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
  /// design/245 — MediaRecorder prepared during listen for this take path.
  String? _primedMicPath;
  /// Per-chunk TTS: one random voice/rate draw; bytes reused for listen+speak.
  Uint8List? _chunkTtsBytes;
  TtsPlaybackParams? _chunkTtsParams;
  /// design/162 — session-only self-view mirror (not persisted).
  bool _mirrorEnabled = false;
  /// design/176 — auto-advance after full listen→speak→my-take cycle.
  final bool _autoAdvance = true;
  /// Invalidate in-flight cycle on give-up / picker jump.
  int _cycleToken = 0;
  /// design/208 — process grooming (rate nudge); copy-free.
  final PracticeGroomingController _grooming = PracticeGroomingController();
  double _groomRateScale = 1.0;
  final PracticeSkillController _skill = PracticeSkillController();
  List<String> _baseChunks = [];
  /// design/214 — minimal rhythm phase + judgment burst.
  RhythmPhase _rhythmPhase = RhythmPhase.idle;
  JudgmentBurstData? _judgmentBurst;
  int _judgmentBurstSeq = 0;
  String? _lastJudgmentCopy;
  bool _judgmentCheers = true;
  ReadingSession? get _session => widget.library.session;

  String get _chunkKey => '$_sentenceId:$_chunkIndex';

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
    _grooming.setServerEnabled(widget.shadowing.groomingServerEnabled);
    _skill.attachClient(widget.client);
    _skill.setServerFlags(
      skill: widget.shadowing.skillServerEnabled,
      cloudStt: widget.shadowing.skillCloudSttEnabled,
      skillEvidence: true,
    );
    unawaited(_skill.bindUid(widget.shadowing.boundUid).then((_) {
      widget.tts.setSkillTier(_skill.tier);
    }));
    unawaited(_loadJudgmentCheersPref());
    unawaited(_boot());
  }

  Future<void> _loadJudgmentCheersPref() async {
    final prefs = await SharedPreferences.getInstance();
    final on = prefs.getBool(kJudgmentCheersPrefKey) ?? true;
    if (mounted) setState(() => _judgmentCheers = on);
  }

  void _showJudgmentBurst(double accuracy) {
    if (!_judgmentCheers || !mounted) return;
    final tier = judgmentTierFor(accuracy);
    final copy = pickJudgmentCopy(tier, lastCopy: _lastJudgmentCopy);
    _lastJudgmentCopy = copy;
    _judgmentBurstSeq += 1;
    setState(() {
      _judgmentBurst = JudgmentBurstData(
        id: _judgmentBurstSeq,
        tier: tier,
        copy: copy,
        accuracyPct: (accuracy * 100).round(),
      );
    });
  }

  void _clearJudgmentBurst(int id) {
    if (!mounted) return;
    if (_judgmentBurst?.id != id) return;
    setState(() => _judgmentBurst = null);
  }

  @override
  void didUpdateWidget(covariant ShadowingPracticeScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    _grooming.setServerEnabled(widget.shadowing.groomingServerEnabled);
    _skill.setServerFlags(
      skill: widget.shadowing.skillServerEnabled,
      cloudStt: widget.shadowing.skillCloudSttEnabled,
      skillEvidence: true,
    );
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
    unawaited(_persistPracticeCursor());
    unawaited(_skill.flushEvidence(cacheId: _cacheId));
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.inactive ||
        state == AppLifecycleState.paused) {
      _focus.onAppPaused(cacheId: _cacheId);
      unawaited(_persistPracticeCursor());
      unawaited(_skill.flushEvidence(cacheId: _cacheId));
    } else if (state == AppLifecycleState.resumed) {
      unawaited(_loadJudgmentCheersPref());
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
    try {
      final st = await widget.client.fetchStatus();
      _skill.spokenCache.setSpeakNorm(st.ttsSpeakNorm);
      _skill.setServerFlags(
        skill: st.mobilePracticeSkill,
        cloudStt: st.mobilePracticeSttCloud,
        skillEvidence: st.mobilePracticeSkillEvidence,
      );
    } catch (_) {}
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

      // design/246 — practice cursor SoT (orthogonal to reading sentenceIndex).
      await _restorePracticeCursor(session);
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
    final key = nav.sentenceBookmarkKeyForGlobal(_sentenceIndex);
    if (_practiceBookmarks.isSentenceBookmarked(key)) {
      await _practiceBookmarks.toggleSentenceBookmark(
        nav,
        _sentenceIndex,
      );
      return;
    }
    final header = nav.headerPartsFor(_sentenceIndex);
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
        _sentenceIndex,
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
      currentGlobalIndex: _sentenceIndex,
      bookmarks: hints,
    );
    if (idx == null || !mounted) return;
    await _goToPracticeSentence(idx);
  }

  /// Skip empty-chunk sentences using local practice cursor (does not move reading).
  /// Returns how many sentences were skipped.
  Future<int> _skipToPlayableSentence(ReadingSession session) async {
    final rows = <({String id, String text})>[
      for (final s in session.sentences) (id: s.id, text: s.text),
    ];
    final delta = shadowingSkipEmptyDelta(
      plan: _plan,
      sentences: rows,
      fromIndex: _sentenceIndex,
    );
    if (delta < 0) {
      _bindSentenceAt(session, _sentenceIndex);
      return 0;
    }
    if (delta > 0) {
      _bindSentenceAt(session, _sentenceIndex + delta);
    } else {
      _bindSentenceAt(session, _sentenceIndex);
    }
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

  void _bindSentenceAt(
    ReadingSession session,
    int globalIndex, {
    int chunkIndex = 0,
  }) {
    final n = session.sentenceCount;
    if (n <= 0) return;
    final i = globalIndex.clamp(0, n - 1);
    _sentenceIndex = i;
    final cur = session.sentences[i];
    _sentenceId =
        (cur.id.trim().isNotEmpty) ? cur.id : '$_sentenceIndex';
    _baseChunks = shadowingChunksForSentence(
      _plan,
      _sentenceId,
      cur.text,
    );
    _chunks = _skill.chunksFor(_baseChunks);
    final maxChunk = _chunks.isEmpty ? 0 : _chunks.length - 1;
    _chunkIndex = chunkIndex.clamp(0, maxChunk);
    unawaited(_prefetchSpoken());
    unawaited(_persistPracticeCursor());
  }

  Future<void> _persistPracticeCursor() async {
    final cid = _cacheId;
    if (cid.isEmpty) return;
    try {
      await savePracticeProgress(
        uid: widget.shadowing.boundUid,
        cacheId: cid,
        sentenceIndex: _sentenceIndex,
        chunkIndex: _chunkIndex,
      );
    } catch (_) {}
  }

  Future<void> _restorePracticeCursor(ReadingSession session) async {
    final stored = await loadPracticeProgress(
      uid: widget.shadowing.boundUid,
      cacheId: _cacheId,
    );
    // First visit: seed from reading position; later opens use practice SoT.
    final seeded = stored ??
        PracticeProgressRow(sentenceIndex: session.sentenceIndex);
    final clamped = clampPracticeProgress(
      raw: seeded,
      sentenceCount: session.sentenceCount,
      chunkCount: 1,
    );
    final startSi =
        clamped?.sentenceIndex ?? session.sentenceIndex.clamp(0, session.sentenceCount - 1);
    final wantChunk = stored?.chunkIndex ?? 0;
    _bindSentenceAt(session, startSi, chunkIndex: wantChunk);
  }

  void _clearChunkTtsCache() {
    _chunkTtsBytes = null;
    _chunkTtsParams = null;
  }

  Future<void> _prefetchSpoken() async {
    if (_chunks.isEmpty) return;
    final i = _chunkIndex.clamp(0, _chunks.length - 1);
    await _skill.ensureSpoken(_displayChunk(i));
  }

  void _reapplyDensity({String? previousText}) {
    final prev = previousText ??
        (_chunks.isEmpty
            ? ''
            : _chunks[_chunkIndex.clamp(0, _chunks.length - 1)]);
    _chunks = _skill.chunksFor(_baseChunks);
    _chunkIndex = rematchChunkIndex(_chunks, prev, _chunkIndex);
    _clearChunkTtsCache();
    widget.tts.setSkillTier(_skill.tier);
    unawaited(_prefetchSpoken());
    unawaited(_persistPracticeCursor());
  }

  /// design/216 — display/spoken/score share one stripped chunk string.
  String _displayChunk([int? index]) {
    if (_chunks.isEmpty) return '';
    final i = (index ?? _chunkIndex).clamp(0, _chunks.length - 1);
    return cite.stripCiteMarkersForDisplay(_chunks[i]);
  }

  Future<void> _ensureChunkTts(String text) async {
    if (_chunkTtsBytes != null && _chunkTtsParams != null) return;
    unawaited(_skill.ensureSpoken(text));
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
    final text = _displayChunk();
    try {
      await _ensureChunkTts(text);
      final bytes = _chunkTtsBytes!;
      final params = _chunkTtsParams!;
      await _player.stop();
      try {
        final effective = clampSpeakingRate(
          params.speakingRate * _groomRateScale,
        );
        await _player.setPlaybackRate(effective);
      } catch (_) {
        // EDGE: player rate unsupported on some devices — still play.
      }
      // Speak-along: lower TTS so the take is not drowned by speaker bleed.
      final vol = phase == 'tts_speak' ? _kSpeakTtsVolume : _kFullTtsVolume;
      try {
        await _player.setVolume(vol);
      } catch (_) {
        // EDGE: volume API missing — play at default.
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
          'tts_volume_pct': phase == 'tts_speak' ? 20 : 100,
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
    _grooming.setServerEnabled(widget.shadowing.groomingServerEnabled);
    _groomRateScale = _focus.sessionActive
        ? _grooming.beginCycle(chunkKey: _chunkKey, cacheId: _cacheId)
        : 1.0;

    bool alive() =>
        mounted &&
        token == _cycleToken &&
        _focus.sessionActive &&
        !_focus.paused;

    setState(() {
      _status = '듣는 중';
      _rhythmPhase = RhythmPhase.listen;
    });
    // design/245 — prepare MediaRecorder while listen TTS plays (no start yet).
    unawaited(_primeMicForUpcomingSpeak());
    try {
      await _playCachedChunkTts(phase: 'tts_listen');
    } catch (_) {
      rethrow;
    }
    if (!alive()) {
      return;
    }

    setState(() => _rhythmPhase = RhythmPhase.speak);
    final speakResult = await _runSpeakPhase();
    if (!alive()) {
      return;
    }
    _grooming.onOutcome(
      obs: GroomingObservation(
        signal: speakResult.signal,
        chunkKey: _chunkKey,
        code: speakResult.code,
      ),
      cacheId: _cacheId,
    );
    if (!speakResult.ok) {
      if (mounted) setState(() => _rhythmPhase = RhythmPhase.idle);
      await Future<void>.delayed(const Duration(milliseconds: 800));
      if (!alive()) return;
      await _advanceToNextChunk(token: token);
      return;
    }

    setState(() => _rhythmPhase = RhythmPhase.replay);
    await _playMyTakePhase();
    if (!alive()) return;
    if (mounted) setState(() => _rhythmPhase = RhythmPhase.idle);
    if (!alive()) return;

    if (_autoAdvance) {
      await _advanceToNextChunk(token: token);
    }
  }

  /// design/245 — build+prepare recorder during listen so Speak start is cheap.
  Future<void> _primeMicForUpcomingSpeak() async {
    try {
      var okMic = await _mic.invokeMethod<bool>('hasPermission') ?? false;
      if (!okMic) {
        okMic = await _mic.invokeMethod<bool>('requestPermission') ?? false;
      }
      if (!okMic) {
        _primedMicPath = null;
        return;
      }
      final dir = await getTemporaryDirectory();
      final path =
          '${dir.path}${Platform.pathSeparator}asr_shadow_${DateTime.now().millisecondsSinceEpoch}.m4a';
      final primed =
          await _mic.invokeMethod<bool>('prepare', {'path': path}) ?? false;
      _primedMicPath = primed ? path : null;
    } catch (_) {
      _primedMicPath = null;
    }
  }

  /// Phase 2 — mic open; focus clock runs only after ready-beat. Reuses chunk TTS.
  Future<_SpeakPhaseResult> _runSpeakPhase() async {
    if (_chunks.isEmpty) {
      return const _SpeakPhaseResult(
        ok: false,
        signal: GroomingSignal.takeFail,
        code: 'no_chunks',
      );
    }
    setState(() => _status = '말할 준비');
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
      _primedMicPath = null;
      return const _SpeakPhaseResult(
        ok: false,
        signal: GroomingSignal.micPerm,
        code: 'mic_perm',
      );
    }
    var path = _primedMicPath;
    if (path == null || path.isEmpty) {
      final dir = await getTemporaryDirectory();
      path =
          '${dir.path}${Platform.pathSeparator}asr_shadow_${DateTime.now().millisecondsSinceEpoch}.m4a';
    }
    final started =
        await _mic.invokeMethod<bool>('start', {'path': path}) ?? false;
    _primedMicPath = null;
    if (!started) {
      asrEvidenceBus?.record(
        'shadowing_loop_event',
        cacheId: _cacheId,
        ok: false,
        code: 'mic_start',
        details: {'phase': 'mic_start', 'ok': false, 'exc_type': 'mic_start'},
      );
      setState(() => _status = '녹음을 시작하지 못했습니다. 다음 구간으로 넘어갑니다.');
      return const _SpeakPhaseResult(
        ok: false,
        signal: GroomingSignal.takeFail,
        code: 'mic_start',
      );
    }
    // design/245 — let the recorder settle; user should not speak yet.
    await Future<void>.delayed(_speakMicReadyBeat);
    if (!mounted) {
      unawaited(_mic.invokeMethod<String>('stop'));
      return const _SpeakPhaseResult(
        ok: false,
        signal: GroomingSignal.takeFail,
        code: 'unmounted',
      );
    }
    setState(() => _status = '말하는 중');
    _focus.beginSpeak();
    asrEvidenceBus?.record(
      'shadowing_loop_event',
      cacheId: _cacheId,
      ok: true,
      details: {
        'phase': 'mic_start',
        'ok': true,
        'mic_ready_ms': _speakMicReadyBeat.inMilliseconds,
      },
    );
    var takeOk = false;
    var signal = GroomingSignal.takeFail;
    var code = 'take_fail';
    var takeByteLen = 0;
    var cloudOk = false;
    final wall = Stopwatch()..start();
    try {
      await _playCachedChunkTts(phase: 'tts_speak');
      await Future<void>.delayed(_pad);
    } finally {
      wall.stop();
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
        signal = GroomingSignal.takeFail;
        code = 'missing_file';
      } else {
        final bytes = await file.readAsBytes();
        if (bytes.isEmpty) {
          setState(() => _status = '녹음이 비었습니다. 다음 구간으로 넘어갑니다.');
          signal = GroomingSignal.takeFail;
          code = 'empty_bytes';
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
            takeByteLen = bytes.length;
            cloudOk = !_localSot;
            setState(() => _status = '저장됨');
            final densBefore = _skill.density;
            final tierBefore = _skill.tier;
            unawaited((() async {
              _skill.setCycleContext(
                cacheId: _cacheId,
                sentenceId: _sentenceId,
                chunkIndex: _chunkIndex,
                focusElapsedMs: _focus.displayElapsed.inMilliseconds,
              );
              final scored = await _skill.onTakeReady(
                chunkDisplay: _displayChunk(),
                takeBytes: bytes,
                mime: 'audio/mp4',
                baseChunks: _baseChunks,
              );
              if (!mounted || scored == null) return;
              if (scored.ok && scored.accuracy != null) {
                _showJudgmentBurst(scored.accuracy!);
              }
              if (_skill.density != densBefore || _skill.tier != tierBefore) {
                _reapplyDensity();
              }
            })());
            final tooShort = await _takeLooksTooShort(
              path: filePath,
              expectedMs: wall.elapsedMilliseconds,
              byteLen: bytes.length,
            );
            if (tooShort) {
              signal = GroomingSignal.takeTooShort;
              code = 'too_short';
            } else {
              signal = GroomingSignal.clean;
              code = 'ok';
            }
          } on AsrApiException catch (e) {
            if (e.statusCode == 409) {
              takeOk = true;
              takeByteLen = bytes.length;
              cloudOk = !_localSot;
              signal = GroomingSignal.clean;
              code = 'ok_409';
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
    var takeDurMs = 0;
    if (takeOk && (_lastTakePath ?? '').isNotEmpty) {
      try {
        final probe = AudioPlayer();
        try {
          await probe.setSource(DeviceFileSource(_lastTakePath!));
          final d = await probe.getDuration();
          takeDurMs = d?.inMilliseconds ?? 0;
        } finally {
          await probe.dispose();
        }
      } catch (_) {}
    }
    return _SpeakPhaseResult(
      ok: takeOk,
      signal: signal,
      code: code,
      wallMs: wall.elapsedMilliseconds,
      takeBytes: takeByteLen,
      takeDurMs: takeDurMs,
      persistOk: takeOk,
      cloudTakeOk: cloudOk,
    );
  }


  /// Heuristic: tiny file or duration ≪ speak wall clock → struggle signal.
  Future<bool> _takeLooksTooShort({
    required String path,
    required int expectedMs,
    required int byteLen,
  }) async {
    if (byteLen > 0 && byteLen < 2500) return true;
    if (expectedMs <= 0) return false;
    try {
      final probe = AudioPlayer();
      try {
        await probe.setSource(DeviceFileSource(path));
        final d = await probe.getDuration();
        if (d == null) return false;
        return d.inMilliseconds < (expectedMs * 0.45).round();
      } finally {
        await probe.dispose();
      }
    } catch (_) {
      return false;
    }
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
      try {
        await _player.setVolume(_kFullTtsVolume);
      } catch (_) {}
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


  String _sectionKeyFor(ReadingSession session) {
    final nav = session.sectionNav;
    final (si, _) = nav.selectionForGlobal(_sentenceIndex);
    return nav.sectionKeyAt(si);
  }

  /// Immersive focus hides section chrome — one-shot cue on section entry only.
  void _announceSectionIfChanged({
    required String? previousKey,
    required ReadingSession session,
  }) {
    if (!_focus.sessionActive) return;
    final key = _sectionKeyFor(session);
    if (key.isEmpty || key == previousKey) return;
    final name = session.sectionNav
        .headerPartsFor(_sentenceIndex)
        .sectionName;
    if (name.isEmpty || !mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    messenger.clearSnackBars();
    messenger.showSnackBar(
      SnackBar(
        content: Text(
          name,
          textAlign: TextAlign.center,
          style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600),
        ),
        duration: const Duration(milliseconds: 1800),
        behavior: SnackBarBehavior.floating,
        backgroundColor: const Color(0xCC2A2A2A),
        margin: const EdgeInsets.fromLTRB(48, 0, 48, 24),
      ),
    );
  }

  Future<void> _advanceToNextChunk({required int token}) async {
    if (!mounted || token != _cycleToken) return;
    final session = _session;
    if (session == null) return;
    _lastTakePath = null;
    _clearChunkTtsCache();
    if (_chunkIndex + 1 < _chunks.length) {
      _chunkIndex += 1;
      unawaited(_persistPracticeCursor());
    } else if (_sentenceIndex + 1 < session.sentenceCount) {
      final prevSection = _sectionKeyFor(session);
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
      _bindSentenceAt(session, _sentenceIndex + 1 + delta);
      final next = _session ?? session;
      _announceSectionIfChanged(previousKey: prevSection, session: next);
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
    _primedMicPath = null;
    unawaited(_persistPracticeCursor());
    if (_focus.speaking) {
      _focus.endSpeak(cacheId: _cacheId);
    }
    _focus.giveUp(cacheId: _cacheId);
    _grooming.resetSession();
    _groomRateScale = 1.0;
    _skill.resetSessionSeq();
    unawaited(_skill.flushEvidence(cacheId: _cacheId));
    _clearChunkTtsCache();
    setState(() {
      _status =
          '집중 종료 · 미완료 10분은 초기화됩니다. 「시작」으로 다시.';
      _rhythmPhase = RhythmPhase.idle;
      _judgmentBurst = null;
    });
  }

  void _openFocusCalendar() {
    unawaited(
      showFocusPracticeCalendarSheet(
        context: context,
        focus: _focus,
        skill: _skill.store,
        skillFeatureOn: widget.shadowing.skillServerEnabled,
      ),
    );
  }

  Future<void> _onRetryBoot() async {
    if (_busy) return;
    await _boot();
  }

  void _onRestartFocus() {
    _grooming.resetSession();
    _groomRateScale = 1.0;
    unawaited(_loadJudgmentCheersPref());
    _focus.startSession(cacheId: _cacheId);
    setState(() {
      _status = '집중 시작. 말할 때만 시계가 갑니다.';
      _rhythmPhase = RhythmPhase.idle;
      _judgmentBurst = null;
    });
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
      final session = _session;
      if (session == null) return;
      final prevSection = _sectionKeyFor(session);
      // design/246 — do not mutate reading sentenceIndex.
      _bindSentenceAt(session, globalIndex);
      _announceSectionIfChanged(previousKey: prevSection, session: session);
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
    final prompt = _displayChunk();
    final theme = Theme.of(context);
    final remaining = _focus.displayRemaining;
    final elapsed = _focus.displayElapsed;
    final blockLabel = formatFocusClock(
      // Tomato-like: show time spent speaking in this block (counts up).
      elapsed,
    );
    final missionLeft = formatFocusClock(remaining);

    final showMirror = _practiceReady && _mirrorEnabled;
    /// Cycle running — hide chrome, enlarge mirror for focus.
    final immersive = _practiceReady && _focus.sessionActive;

    final phaseAccent = rhythmAccentFor(_rhythmPhase);

    return Scaffold(
      backgroundColor: kRhythmStage,
      appBar: AppBar(
        backgroundColor: kRhythmStage,
        foregroundColor: kRhythmText,
        elevation: 0,
        title: immersive ? null : const Text('따라 말하기'),
        actions: immersive
            ? const []
            : [
                IconButton(
                  icon: const Icon(
                    Icons.calendar_month_outlined,
                    color: kRhythmTextMuted,
                  ),
                  tooltip: '연습 캘린더',
                  onPressed: _openFocusCalendar,
                ),
                if (_practiceReady)
                  IconButton(
                    icon: Icon(
                      _mirrorEnabled
                          ? Icons.videocam
                          : Icons.videocam_off_outlined,
                      color: kRhythmTextMuted,
                    ),
                    tooltip: _mirrorEnabled ? '카메라 끄기' : '카메라 켜기',
                    onPressed: _busy ? null : _toggleMirror,
                  ),
              ],
      ),
      body: Column(
        children: [
          AnimatedContainer(
            duration: const Duration(milliseconds: 180),
            height: 2,
            width: double.infinity,
            color: _focus.sessionActive ? phaseAccent : kRhythmRailIdle,
          ),
          Expanded(
            child: SafeArea(
              top: false,
              child: Padding(
                padding: EdgeInsets.fromLTRB(20, immersive ? 4 : 8, 20, 16),
                child: Stack(
                  children: [
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        if (!_practiceReady)
                          Text(
                            '연습 준비',
                            textAlign: TextAlign.center,
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: kRhythmTextMuted,
                            ),
                          )
                        else if (!immersive) ...[
                          Builder(
                            builder: (context) {
                              final session = _session;
                              if (session == null ||
                                  session.sentenceCount == 0) {
                                return Text(
                                  '문장 없음',
                                  textAlign: TextAlign.center,
                                  style: theme.textTheme.bodySmall?.copyWith(
                                    color: kRhythmTextMuted,
                                  ),
                                );
                              }
                              final nav = session.sectionNav;
                              final header =
                                  nav.headerPartsFor(_sentenceIndex);
                              final sentKey = nav
                                  .sentenceBookmarkKeyForGlobal(
                                      _sentenceIndex);
                              final highlighted = _practiceBookmarks
                                  .isSentenceBookmarked(sentKey);
                              final sectionBadge =
                                  _practiceBookmarks.sectionBadgeCount(
                                nav,
                                _sentenceIndex,
                              );
                              final canPick = nav.sectionCount > 0;
                              return Column(
                                children: [
                                  Theme(
                                    data: Theme.of(context).copyWith(
                                      textTheme:
                                          Theme.of(context).textTheme.apply(
                                                bodyColor: kRhythmTextMuted,
                                                displayColor: kRhythmTextMuted,
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
                                      onTap: _busy
                                          ? null
                                          : _handlePracticeBookmarkTap,
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
                                      color: kRhythmTextMuted.withValues(
                                        alpha: 0.55,
                                      ),
                                    ),
                                  ),
                                ],
                              );
                            },
                          ),
                        ],
                        if (_practiceReady && _focus.sessionActive) ...[
                          const SizedBox(height: 8),
                          RhythmPhaseRail(phase: _rhythmPhase),
                        ],
                        if (showMirror) ...[
                          SizedBox(height: immersive ? 4 : 8),
                          SizedBox(
                            height: MediaQuery.sizeOf(context).height *
                                (immersive ? 0.34 : 0.18),
                            child: const PracticeMirrorPanel(),
                          ),
                        ],
                        SizedBox(height: immersive ? 8 : 12),
                        // Sentence ABOVE timer (design/176).
                        Expanded(
                          flex: immersive && showMirror ? 2 : 3,
                          child: Center(
                            child: SingleChildScrollView(
                              child: Text(
                                prompt.isEmpty ? '…' : prompt,
                                textAlign: TextAlign.center,
                                style:
                                    theme.textTheme.headlineSmall?.copyWith(
                                  color: kRhythmText,
                                  height: 1.35,
                                  letterSpacing: -0.2,
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
                            color: kRhythmText,
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
                                ? kRhythmGreat
                                : kRhythmTextMuted,
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
                                  : kRhythmTextMuted.withValues(alpha: 0.75),
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
                                foregroundColor: kRhythmTextMuted,
                                side: const BorderSide(color: kRhythmRailIdle),
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
                                backgroundColor: kRhythmSpeak,
                                foregroundColor: kRhythmText,
                              ),
                              onPressed: _busy ? null : _onRestartFocus,
                              child: const Text('시작'),
                            ),
                          ),
                      ],
                    ),
                    if (_judgmentBurst != null)
                      Positioned.fill(
                        child: IgnorePointer(
                          child: Center(
                            child: JudgmentBurst(
                              key: ValueKey(_judgmentBurst!.id),
                              data: _judgmentBurst!,
                              onFinished: () =>
                                  _clearJudgmentBurst(_judgmentBurst!.id),
                            ),
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SpeakPhaseResult {
  const _SpeakPhaseResult({
    required this.ok,
    required this.signal,
    required this.code,
    this.wallMs = 0,
    this.takeBytes = 0,
    this.takeDurMs = 0,
    this.persistOk = false,
    this.cloudTakeOk = false,
  });

  final bool ok;
  final GroomingSignal signal;
  final String code;
  final int wallMs;
  final int takeBytes;
  final int takeDurMs;
  final bool persistOk;
  final bool cloudTakeOk;
}
