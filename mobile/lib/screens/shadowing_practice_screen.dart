/// design/82+120+176+214+245+259 — shadowing practice + minimal rhythm + judgment cheers.
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
import '../practice_rhythm/blank_rest.dart';
import '../practice_rhythm/judgment_burst.dart';
import '../practice_rhythm/judgment_copy.dart';
import '../practice_rhythm/judgment_prefs.dart';
import '../practice_rhythm/judgment_tier.dart';
import '../practice_rhythm/phase_rail.dart';
import '../practice_rhythm/follow_span.dart';
import '../practice_rhythm/miss_review.dart';
import '../practice_rhythm/word_phone_text.dart';
import '../practice_rhythm/rhythm_theme.dart';
import '../practice_skill/chunk_density.dart';
import '../practice_skill/practice_skill_controller.dart';
import '../practice_skill/skill_score.dart';
import '../services/evidence_bus.dart';
import '../services/shadowing_disk_store.dart';
import '../services/tts_audio_cache.dart';
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
  /// design/245+259 — after mic start, brief beat before speak UI / guide TTS.
  static const _speakMicReadyBeat = Duration(milliseconds: 350);
  // WHY: design/82 — Android MediaRecorder via platform channel (no pub `record` dep).
  static const _mic = MethodChannel('asr/shadowing_mic');
  /// Speak phase only — quieter guide so mic take keeps user voice (design/206+215+255).
  static const double _kSpeakTtsVolume = 0.05;
  static const double _kFullTtsVolume = 1.0;

  final _player = AudioPlayer();
  final _promptScroll = ScrollController();
  StreamSubscription<Duration>? _followPosSub;
  StreamSubscription<Duration>? _followDurSub;
  int _followGen = 0;
  ({int start, int end})? _follow;
  int _lastPlayerMs = -1;
  int _lastAudioBytes = -1;
  late final FocusPracticeController _focus;
  late final bool _ownsFocus;
  final ShadowingDiskStore _disk = ShadowingDiskStore();
  final TtsAudioCache _ttsAudio = TtsAudioCache();
  final PracticeBookmarkController _practiceBookmarks =
      PracticeBookmarkController();

  String? _status;
  bool _busy = false;
  /// Prep/boot failed — show 「다시 시도」 (not a dead-end status string).
  bool _bootFailed = false;
  /// Plan bound and at least one playable chunk — unlock loop chrome / mirror.
  bool _practiceReady = false;
  /// design/267 — density→rate bias (status kill).
  bool _rateBiasEnabled = true;
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
  int _heardSkillTier = 2;
  bool _heardRandomAuto = false;
  String? _heardVoice;
  double? _heardClientRate;
  String? _reviewWord;
  String _reviewTargetPhone = '';
  String _reviewHeardPhone = '';
  List<String> _reviewDrillPhones = const [];
  bool _missReviewActive = false;
  /// design/162 — session-only self-view mirror (not persisted).
  bool _mirrorEnabled = false;
  /// design/176 — auto-advance after full listen→speak→my-take cycle.
  final bool _autoAdvance = true;
  /// Invalidate in-flight cycle on give-up / picker jump.
  int _cycleToken = 0;
  /// design/320 — rest cover epoch; watchdog invalidates a stuck delay.
  int _restEpoch = 0;
  Timer? _restWatchdog;
  /// design/208 — process grooming (rate nudge); copy-free.
  final PracticeGroomingController _grooming = PracticeGroomingController();
  double _groomRateScale = 1.0;
  final PracticeSkillController _skill = PracticeSkillController();
  List<MissedWordSpan> _replayMisses = const [];
  int _replayMissChunk = -1;
  List<String> _baseChunks = [];
  /// design/214 — minimal rhythm phase + judgment burst.
  RhythmPhase _rhythmPhase = RhythmPhase.idle;
  JudgmentBurstData? _judgmentBurst;
  int _judgmentBurstSeq = 0;
  String? _lastJudgmentCopy;
  bool _judgmentCheers = true;
  /// design/274 — blank rest after Replay (Settings).
  bool _blankRestEnabled = true;
  /// design/274 — defer density rematch until cycle advance.
  bool _pendingDensityRematch = false;
  /// design/207+268 — center section cue while non-null.
  String? _sectionCueName;
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
    _focus.onBlockCompleted = _onFocusBlockCompleted;
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
    unawaited(_loadBlankRestPref());
    unawaited(_boot());
  }

  Future<void> _loadJudgmentCheersPref() async {
    final prefs = await SharedPreferences.getInstance();
    final on = prefs.getBool(kJudgmentCheersPrefKey) ?? true;
    if (mounted) setState(() => _judgmentCheers = on);
  }

  Future<void> _loadBlankRestPref() async {
    final prefs = await SharedPreferences.getInstance();
    final on = prefs.getBool(kBlankRestPrefKey) ?? true;
    if (mounted) setState(() => _blankRestEnabled = on);
  }

  void _onFocusBlockCompleted() {
    unawaited(_handleFocusBlockDone());
  }

  Future<void> _handleFocusBlockDone() async {
    final densBefore = _skill.density;
    final tierBefore = _skill.tier;
    await _skill.onFocusBlockDone(_baseChunks);
    if (!mounted) return;
    if (_skill.density != densBefore || _skill.tier != tierBefore) {
      _pendingDensityRematch = true;
    }
  }

  void _flushPendingDensityRematch() {
    if (!_pendingDensityRematch) return;
    _pendingDensityRematch = false;
    _reapplyDensity();
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
    _focus.onBlockCompleted = null;
    _focus.removeListener(_onFocusTick);
    if (_focus.speaking) {
      _focus.endSpeak(cacheId: _cacheId);
    }
    if (_ownsFocus) {
      _focus.dispose();
    }
    _practiceBookmarks.dispose();
    _followGen++;
    unawaited(_followPosSub?.cancel());
    unawaited(_followDurSub?.cancel());
    _promptScroll.dispose();
    _restWatchdog?.cancel();
    _restWatchdog = null;
    _restEpoch++;
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
      if (_missReviewActive) {
        unawaited(_player.stop());
      }
      unawaited(_persistPracticeCursor());
      unawaited(_skill.flushEvidence(cacheId: _cacheId));
    } else if (state == AppLifecycleState.resumed) {
      unawaited(_loadJudgmentCheersPref());
      unawaited(_loadBlankRestPref());
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
    if (!mounted || !_busy) return;
    if (!_practiceReady) {
      setState(() => _status = _prepStatusLine());
      return;
    }
    // design/266 — merge new ready sentences while practicing.
    if (shadowingPlanStatusIsOk(_plan)) return;
    unawaited(_mergeLatestPlan());
  }

  Future<void> _mergeLatestPlan() async {
    final cacheId = _cacheId;
    if (cacheId.isEmpty || !mounted) return;
    Map<String, dynamic>? latest = await _disk.loadChunkPlanJson(cacheId);
    if (latest == null || latest['status']?.toString() == 'error') {
      try {
        final got = await widget.client.fetchShadowingChunks(cacheId);
        final p = got['plan'];
        if (p is Map) latest = Map<String, dynamic>.from(p);
      } catch (_) {}
    }
    if (latest == null || !mounted) return;
    final before = countShadowingReadySentences(_plan);
    _plan = mergeShadowingPlans(_plan, latest);
    final after = countShadowingReadySentences(_plan);
    if (after > before) {
      asrEvidenceBus?.record(
        'shadowing_plan_merge',
        cacheId: cacheId,
        severity: 'lifecycle',
        ok: true,
        details: {
          'ready_before': before,
          'ready_after': after,
          'plan_status': _plan?['status']?.toString() ?? '',
        },
      );
    }
    final session = _session;
    if (session != null && _chunks.isEmpty) {
      await _skipToPlayableSentence(session);
    }
    if (mounted) setState(() {});
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
      _rateBiasEnabled =
          st.mobilePracticeRateBias && st.mobilePracticeSkill;
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

      // design/266 — accept pending with ≥1 ready sentence; continue ensure.
      Map<String, dynamic>? plan = await _disk.loadChunkPlanJson(cacheId);
      if (countShadowingReadySentences(plan) < 1) {
        try {
          final got = await widget.client.fetchShadowingChunks(cacheId);
          final p = got['plan'];
          if (p is Map) {
            plan = Map<String, dynamic>.from(p);
            if (countShadowingReadySentences(plan) >= 1 ||
                shadowingPlanStatusIsPending(plan) ||
                shadowingPlanStatusIsOk(plan)) {
              unawaited(_disk.writeChunkPlanJson(cacheId, plan));
            }
          }
        } catch (_) {
          // Fall through to library ensure.
        }
      }

      if (countShadowingReadySentences(plan) < 1) {
        if (!mounted) return;
        setState(() => _status = _prepStatusLine());
        await widget.library.ensureShadowingChunks(
          cacheId,
          trigger: 'practice_boot',
        );
        rounds = 1;
        plan = await _disk.loadChunkPlanJson(cacheId);
        if (countShadowingReadySentences(plan) < 1) {
          try {
            final got = await widget.client.fetchShadowingChunks(cacheId);
            final p = got['plan'];
            if (p is Map) plan = Map<String, dynamic>.from(p);
          } catch (_) {}
        }
      }

      final readyN = countShadowingReadySentences(plan);
      if (readyN < 1) {
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

      planStatus = plan?['status']?.toString() ?? '';
      _plan = Map<String, dynamic>.from(plan!);
      unawaited(_disk.writeChunkPlanJson(cacheId, _plan!));

      // Keep building remaining sentences while user practices.
      if (!shadowingPlanStatusIsOk(_plan)) {
        unawaited(
          widget.library.ensureShadowingChunks(
            cacheId,
            trigger: 'practice_background',
          ),
        );
      }

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
          'ready_sentence_n': readyN,
          'partial_ready': shadowingPlanStatusIsOk(_plan) ? 0 : 1,
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
      String sectionLabel = '';
      final s = _session;
      if (s != null && s.isValid) {
        final header = s.sectionNav.headerPartsFor(_sentenceIndex);
        sectionLabel = '${header.sectionName} ${header.rightLabel}'.trim();
      }
      await widget.library.recordPracticeProgress(
        cacheId: cid,
        sentenceIndex: _sentenceIndex,
        chunkIndex: _chunkIndex,
        sectionLabel: sectionLabel,
      );
    } catch (_) {}
  }

  Future<void> _restorePracticeCursor(ReadingSession session) async {
    final stored = await widget.library.loadPracticeProgressRow(_cacheId);
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
    unawaited(_skill.warmPhonemeModel());
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
    // Spans must be stored before play. Spoken failure still allows audio.
    final spoken = _skill.ensureSpoken(text);
    final bias = _rateBiasEnabled && _skill.serverEnabled;
    final params = widget.tts.pickPlaybackParams(
      practiceDensity: _skill.density,
      applyDensityRateBias: bias,
    );
    final audioKey = ttsAudioKey(
      text: text,
      voice: params.voice,
      rate: kTtsRateDefault,
      speakNorm: _skill.spokenCache.speakNorm,
    );
    final cachedAudio = await _ttsAudio.read(audioKey);
    final audio = cachedAudio != null
        ? Future<Uint8List>.value(cachedAudio)
        : widget.client.synthesizeTts(
            text: text,
            voice: params.voice,
            speakingRate: kTtsRateDefault,
            // design/343 — this paper's own compound names.
            cacheId: _cacheId,
          );
    final results = await Future.wait<Object?>([spoken, audio]);
    final bytes = results[1]! as List<int>;
    if (cachedAudio == null) {
      unawaited(_ttsAudio.write(audioKey, bytes));
    }
    _chunkTtsBytes = Uint8List.fromList(bytes);
    _chunkTtsParams = params;
  }

  void _clearFollowLight() {
    _followGen++;
    unawaited(_followPosSub?.cancel());
    unawaited(_followDurSub?.cancel());
    _followPosSub = null;
    _followDurSub = null;
    if (_follow == null) return;
    _follow = null;
    if (mounted) setState(() {});
  }

  TextStyle _promptStyle(ThemeData theme) {
    return (theme.textTheme.headlineSmall ?? const TextStyle()).copyWith(
      color: kRhythmText,
      height: 1.35,
      letterSpacing: -0.2,
      fontWeight: FontWeight.w500,
    );
  }

  double _promptMaxWidth = 0;

  void _armFollowLight({
    required String text,
    required int token,
    required int chunk,
  }) {
    _clearFollowLight();
    final spans = _skill.spokenCache.peekSpans(text);
    if (spans.isEmpty) return;
    final gen = _followGen;
    Duration? mediaDur;
    _followPosSub = _player.onPositionChanged.listen((pos) {
      if (!mounted || gen != _followGen) return;
      if (token != _cycleToken || chunk != _chunkIndex) return;
      if (_rhythmPhase != RhythmPhase.listen &&
          _rhythmPhase != RhythmPhase.speak) {
        return;
      }
      final dms = mediaDur?.inMilliseconds ?? 0;
      if (dms <= 0) return;
      // File clock. Do not divide by playback rate (design/313).
      final hit = activeFollowSpan(spans, pos.inMilliseconds, dms);
      final next = hit == null ? null : (start: hit.start, end: hit.end);
      if (next?.start == _follow?.start && next?.end == _follow?.end) return;
      setState(() => _follow = next);
      _queueFollowScroll(text);
    });
    _followDurSub = _player.onDurationChanged.listen((d) {
      if (gen != _followGen) return;
      mediaDur = d;
    });
  }

  void _queueFollowScroll(String text) {
    final span = _follow;
    if (span == null || !_promptScroll.hasClients) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_promptScroll.hasClients) return;
      final width = _promptMaxWidth > 0
          ? _promptMaxWidth
          : MediaQuery.sizeOf(context).width;
      final target = followRevealOffset(
        text: text,
        style: _promptStyle(Theme.of(context)),
        start: span.start,
        end: span.end,
        maxWidth: width,
        viewportHeight: _promptScroll.position.viewportDimension,
        currentOffset: _promptScroll.offset,
      );
      if (target == null) return;
      unawaited(
        _promptScroll.animateTo(
          target,
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOut,
        ),
      );
    });
  }

  Future<void> _playCachedChunkTts({required String phase}) async {
    final text = _displayChunk();
    var headset = true;
    if (phase == 'tts_speak') {
      headset = await _mic.invokeMethod<bool>('hasHeadset') ?? false;
    }
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
        _heardSkillTier = widget.tts.skillTier;
        _heardRandomAuto = widget.tts.mode == kTtsModeRandomAuto;
        _heardVoice = params.voice;
        _heardClientRate = effective;
      } catch (_) {
        // EDGE: player rate unsupported on some devices — still play.
      }
      // Speak-along: lower TTS so the take is not drowned by speaker bleed.
      final vol = !headset
          ? 0.0
          : (phase == 'tts_speak' ? _kSpeakTtsVolume : _kFullTtsVolume);
      try {
        await _player.setVolume(vol);
      } catch (_) {
        // EDGE: volume API missing — play at default.
      }
      final done = _player.onPlayerComplete.first;
      if (phase == 'tts_listen' || phase == 'tts_speak') {
        _armFollowLight(
          text: text,
          token: _cycleToken,
          chunk: _chunkIndex,
        );
      } else {
        _clearFollowLight();
      }
      final playerSw = Stopwatch()..start();
      try {
        await _player.play(BytesSource(bytes));
        await done;
      } finally {
        playerSw.stop();
        _lastPlayerMs = playerSw.elapsedMilliseconds;
        _lastAudioBytes = bytes.length;
        _clearFollowLight();
      }
      asrEvidenceBus?.record(
        'shadowing_loop_event',
        cacheId: _cacheId,
        ok: true,
        details: {
          'phase': phase,
          'ok': true,
          'tts_reuse': phase == 'tts_speak' ? 1 : 0,
          'tts_volume_pct': phase == 'tts_speak' ? 5 : 100,
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
      _replayMisses = const [];
      _replayMissChunk = -1;
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

    // design/259 — keep Listen UI through mic ready-beat; Speak chrome in
    // `_revealSpeakUi` together with beginSpeak / 「말하는 중」.
    final speakResult = await _runSpeakPhase(token: token);
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
      await _advanceToNextChunk(token: token, withRest: false);
      return;
    }
    if (_chunks.isNotEmpty && _chunkIndex >= _chunks.length - 1) {
      await _focus.noteFullSentenceRead();
    }

    setState(() => _rhythmPhase = RhythmPhase.replay);
    await _playMyTakePhase();
    if (!alive()) return;
    if (mounted) setState(() => _rhythmPhase = RhythmPhase.idle);
    if (!alive()) return;

    var reviewWords = const <String>[];
    final score = speakResult.score;
    if (score != null) {
      try {
        final snap = await score.timeout(kMissReviewScoreWait);
        if (snap != null) {
          reviewWords = missReviewWords(
            display: snap.display,
            spans: snap.spans,
          );
        }
      } catch (_) {
        reviewWords = const [];
      }
    }
    if (!alive()) return;

    if (_autoAdvance) {
      await _advanceToNextChunk(
        token: token,
        withRest: true,
        reviewWords: reviewWords,
      );
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

  /// design/259 — flip Speak rail/status at the same tick as beginSpeak.
  void _revealSpeakUi() {
    setState(() {
      _rhythmPhase = RhythmPhase.speak;
      _status = '말하는 중';
    });
    _focus.beginSpeak();
  }

  /// Phase 2 — mic open; focus clock runs only after ready-beat. Reuses chunk TTS.
  /// UI stays Listen until `_revealSpeakUi` (design/259).
  /// design/260 — after ready beat, require cycle [token] still alive.
  Future<_SpeakPhaseResult> _runSpeakPhase({required int token}) async {
    if (_chunks.isEmpty) {
      return const _SpeakPhaseResult(
        ok: false,
        signal: GroomingSignal.takeFail,
        code: 'no_chunks',
      );
    }
    bool alive() =>
        mounted &&
        token == _cycleToken &&
        _focus.sessionActive &&
        !_focus.paused;
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
    // design/245 — let the recorder settle; design/259 — UI still Listen here.
    await Future<void>.delayed(_speakMicReadyBeat);
    // design/260 — Give Up / jump / pause during beat must not reveal Speak.
    if (!alive()) {
      unawaited(_mic.invokeMethod<String>('stop'));
      return const _SpeakPhaseResult(
        ok: false,
        signal: GroomingSignal.takeFail,
        code: 'cycle_cancelled',
      );
    }
    _revealSpeakUi();
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
    Future<({String display, List<MissedWordSpan> spans})?>? scoreFuture;
    final wall = Stopwatch()..start();
    var callMs = -1;
    var padMs = 0;
    var playCode = 'played';
    var fileMs = -1;
    var tooShortFlag = 0;
    try {
      final callSw = Stopwatch()..start();
      try {
        await _playCachedChunkTts(phase: 'tts_speak');
        callSw.stop();
        callMs = callSw.elapsedMilliseconds;
      } catch (_) {
        callSw.stop();
        callMs = callSw.elapsedMilliseconds;
        playCode = 'play_threw';
        rethrow;
      }
      final padSw = Stopwatch()..start();
      await Future<void>.delayed(_pad);
      padSw.stop();
      padMs = padSw.elapsedMilliseconds;
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
            final scoredChunk = _chunkIndex;
            final chunkDisplay = _displayChunk();
            scoreFuture = _finishTakeScore(
              chunkDisplay: chunkDisplay,
              scoredChunk: scoredChunk,
              bytes: bytes,
              densBefore: densBefore,
              tierBefore: tierBefore,
            );
            final tooShort = await _takeLooksTooShort(
              path: filePath,
              expectedMs: wall.elapsedMilliseconds,
              byteLen: bytes.length,
            );
            if (tooShort) {
              signal = GroomingSignal.takeTooShort;
              code = 'too_short';
              tooShortFlag = 1;
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
      if (takeOk && (_lastTakePath ?? '').isNotEmpty) {
        try {
          final probe = AudioPlayer();
          try {
            await probe.setSource(DeviceFileSource(_lastTakePath!));
            final d = await probe.getDuration();
            fileMs = d?.inMilliseconds ?? -1;
          } finally {
            await probe.dispose();
          }
        } catch (_) {}
      }
      await _skill.noteSpeakWindow(
        wallMs: wall.elapsedMilliseconds,
        callMs: callMs,
        playerMs: _lastPlayerMs,
        padMs: padMs,
        fileMs: fileMs,
        fileBytes: takeByteLen,
        audioBytes: _lastAudioBytes,
        tooShort: tooShortFlag,
        playCode: playCode,
      );
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
      score: scoreFuture,
    );
  }

  Future<({String display, List<MissedWordSpan> spans})?> _finishTakeScore({
    required String chunkDisplay,
    required int scoredChunk,
    required List<int> bytes,
    required int densBefore,
    required int tierBefore,
  }) async {
    _skill.setCycleContext(
      cacheId: _cacheId,
      sentenceId: _sentenceId,
      chunkIndex: scoredChunk,
      focusElapsedMs: _focus.displayElapsed.inMilliseconds,
    );
    final scored = await _skill.onTakeReady(
      chunkDisplay: chunkDisplay,
      takeBytes: bytes,
      mime: 'audio/mp4',
      baseChunks: _baseChunks,
    );
    if (!mounted || scored == null) {
      return (display: chunkDisplay, spans: const <MissedWordSpan>[]);
    }
    if (scoredChunk == _chunkIndex) {
      setState(() {
        _replayMisses = scored.missedSpans;
        _replayMissChunk = scoredChunk;
      });
    }
    if (scored.ok && scored.accuracy != null) {
      _showJudgmentBurst(scored.accuracy!);
    }
    if (_skill.density != densBefore || _skill.tier != tierBefore) {
      _reapplyDensity();
    }
    return (display: chunkDisplay, spans: scored.missedSpans);
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
    _clearFollowLight();
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

  /// Immersive focus — center one-shot section name (design/207+268).
  Future<void> _showSectionCueIfChanged({
    required String? previousKey,
    required ReadingSession session,
    required int token,
  }) async {
    if (!_focus.sessionActive) return;
    final key = _sectionKeyFor(session);
    if (key.isEmpty || key == previousKey) return;
    final name = session.sectionNav
        .headerPartsFor(_sentenceIndex)
        .sectionName;
    if (name.isEmpty || !mounted) return;
    setState(() => _sectionCueName = name);
    await Future<void>.delayed(const Duration(milliseconds: 2000));
    if (!mounted || token != _cycleToken) return;
    setState(() => _sectionCueName = null);
  }

  void _clearRestWatchdog() {
    _restWatchdog?.cancel();
    _restWatchdog = null;
  }

  void _armRestWatchdog({
    required int token,
    required int epoch,
    required Duration limit,
  }) {
    _clearRestWatchdog();
    if (limit <= Duration.zero) return;
    _restWatchdog = Timer(limit, () {
      unawaited(_onRestCoverWatchdog(token: token, epoch: epoch));
    });
  }

  Future<void> _onRestCoverWatchdog({
    required int token,
    required int epoch,
  }) async {
    if (!mounted || epoch != _restEpoch || token != _cycleToken) return;
    if (_rhythmPhase != RhythmPhase.rest) return;
    _restEpoch++;
    _cycleToken++;
    _clearRestWatchdog();
    asrEvidenceBus?.record(
      'shadowing_loop_event',
      cacheId: _cacheId,
      ok: false,
      code: 'rest_overrun',
      details: {
        'phase': 'rest_cover',
        'ok': false,
        'chunk_index': _chunkIndex,
        'chunk_n': _chunks.length,
      },
    );
    unawaited(_player.stop());
    setState(() {
      _rhythmPhase = RhythmPhase.idle;
      _reviewWord = null;
    });
    if (!_focus.sessionActive || _focus.paused) return;
    await _runCycle();
  }

  Future<bool> _awaitRestDeadline({
    required int token,
    required int epoch,
    required DateTime deadline,
  }) async {
    while (DateTime.now().isBefore(deadline)) {
      if (!mounted || token != _cycleToken || epoch != _restEpoch) {
        return false;
      }
      if (!_focus.sessionActive || _focus.paused) return false;
      final left = deadline.difference(DateTime.now());
      final slice = left < const Duration(milliseconds: 400)
          ? left
          : const Duration(milliseconds: 400);
      if (slice <= Duration.zero) break;
      await Future<void>.delayed(slice);
    }
    return mounted && token == _cycleToken && epoch == _restEpoch;
  }

  bool _reviewAlive(int token) =>
      mounted &&
      token == _cycleToken &&
      _focus.sessionActive &&
      !_focus.paused;

  Future<void> _runMissReview({
    required int token,
    required List<String> words,
    required Duration scheduledRest,
    required int reviewTier,
    required bool randomAuto,
    required String? voice,
    required double? clientRate,
  }) async {
    if (words.isEmpty || !_reviewAlive(token)) return;
    _missReviewActive = true;
    final clock = Stopwatch()..start();
    final epoch = ++_restEpoch;
    _armRestWatchdog(
      token: token,
      epoch: epoch,
      limit: restCoverWatchdogLimit(
        scheduledRest: scheduledRest,
        reviewWordN: words.length,
      ),
    );
    setState(() {
      _rhythmPhase = RhythmPhase.rest;
      _reviewWord = null;
      _reviewDrillPhones = const [];
      _judgmentBurst = null;
    });
    try {
      for (var i = 0; i < words.length; i++) {
        if (!_reviewAlive(token)) return;
        String? avoidVoice;
        double? avoidRate;
        for (var attempt = 0; attempt < kMissReviewMaxTries; attempt++) {
          if (!_reviewAlive(token)) return;
          final draw = drawMissReviewPlayback(
            randomAuto: randomAuto || attempt > 0,
            reviewTier: reviewTier,
            fallbackVoice: voice ?? widget.tts.voice,
            fallbackRate: clientRate ?? kTtsRateDefault,
            voiceIds:
                widget.tts.voices.map((v) => v.id).toList(growable: false),
            avoidVoice: attempt == 0 ? null : avoidVoice,
            avoidRate: attempt == 0 ? null : avoidRate,
          );
          final played = await _playReviewWord(
            token: token,
            word: words[i],
            playVoice: draw.voice,
            playRate: draw.rate,
          );
          if (!_reviewAlive(token)) return;
          if (!played.ok) break;
          avoidVoice = draw.voice;
          avoidRate = draw.rate;
          final hear = await _hearReviewWord(
            token: token,
            word: words[i],
            ttsHeard: played.heard,
            attempt: attempt,
            wordIndex: i,
          );
          if (!_reviewAlive(token)) return;
          if (hear != MissReviewHear.missed) break;
        }
        if (mounted) setState(() => _reviewWord = null);
        if (i + 1 < words.length) {
          await Future<void>.delayed(kMissReviewGap);
        }
      }
      if (!_reviewAlive(token)) return;
      clock.stop();
      final tail = missReviewTail(
        scheduledRest: scheduledRest,
        elapsed: clock.elapsed,
      );
      if (tail > Duration.zero) {
        if (mounted) {
          setState(() {
            _rhythmPhase = RhythmPhase.rest;
            _reviewWord = null;
          });
        }
        final still = await _awaitRestDeadline(
          token: token,
          epoch: epoch,
          deadline: DateTime.now().add(tail),
        );
        if (!still) return;
      }
    } finally {
      _missReviewActive = false;
      final stillThisCover = epoch == _restEpoch;
      if (stillThisCover) _clearRestWatchdog();
      if (!mounted) {
        // cover already gone with the widget
      } else if (!_reviewAlive(token) &&
          stillThisCover &&
          _rhythmPhase == RhythmPhase.rest) {
        setState(() {
          _rhythmPhase = RhythmPhase.idle;
          _reviewWord = null;
        });
      } else {
        setState(() => _reviewWord = null);
      }
    }
  }

  Future<({bool ok, Duration heard})> _playReviewWord({
    required int token,
    required String word,
    required String playVoice,
    required double playRate,
  }) async {
    const silent = (ok: false, heard: Duration.zero);
    if (!_reviewAlive(token)) return silent;
    _clearFollowLight();
    if (mounted) setState(() => _reviewWord = word);
    try {
      await _player.stop();
      await _player.setVolume(_kFullTtsVolume);
      await _player.setPlaybackRate(clampSpeakingRate(playRate));
      final wordKey = ttsAudioKey(
        text: word,
        voice: playVoice,
        rate: kTtsRateDefault,
        speakNorm: _skill.spokenCache.speakNorm,
      );
      var bytes = await _ttsAudio.read(wordKey) ?? Uint8List(0);
      if (bytes.isEmpty) {
        bytes = await widget.client
            .synthesizeTts(
              text: word,
              voice: playVoice,
              speakingRate: kTtsRateDefault,
              cacheId: _cacheId,
            )
            .timeout(kMissReviewWordTimeout);
        unawaited(_ttsAudio.write(wordKey, bytes));
      }
      if (!_reviewAlive(token) || bytes.isEmpty) return silent;
      if (mounted && _reviewWord != word) {
        setState(() => _reviewWord = word);
      }
      final done = _player.onPlayerComplete.first.timeout(kMissReviewWordTimeout);
      final wall = Stopwatch()..start();
      await _player.play(BytesSource(bytes));
      await done;
      wall.stop();
      await _player.stop();
      if (!_reviewAlive(token)) return silent;
      return (ok: true, heard: wall.elapsed);
    } catch (_) {
      if (mounted) setState(() => _reviewWord = null);
      return silent;
    }
  }

  /// Record after TTS has stopped. The take must not contain the model voice.
  Future<MissReviewHear> _hearReviewWord({
    required int token,
    required String word,
    required Duration ttsHeard,
    required int attempt,
    required int wordIndex,
  }) async {
    if (!_skill.serverEnabled || !_skill.cloudSttEnabled) {
      return MissReviewHear.skip;
    }
    if (!_reviewAlive(token)) return MissReviewHear.skip;
    var started = false;
    try {
      await _player.stop();
      var okMic = await _mic.invokeMethod<bool>('hasPermission') ?? false;
      if (!okMic) {
        okMic = await _mic.invokeMethod<bool>('requestPermission') ?? false;
      }
      if (!okMic || !_reviewAlive(token)) return MissReviewHear.skip;
      await Future<void>.delayed(kMissReviewMicReady);
      if (!_reviewAlive(token)) return MissReviewHear.skip;
      final dir = await getTemporaryDirectory();
      final path =
          '${dir.path}${Platform.pathSeparator}asr_review_${DateTime.now().millisecondsSinceEpoch}.m4a';
      started = await _mic.invokeMethod<bool>('start', {'path': path}) ?? false;
      if (!started || !_reviewAlive(token)) return MissReviewHear.skip;
      await Future<void>.delayed(missReviewSpeakWindow(ttsHeard));
      if (!_reviewAlive(token)) return MissReviewHear.skip;
      final outPath = await _mic.invokeMethod<String>('stop');
      started = false;
      final filePath = (outPath == null || outPath.isEmpty) ? path : outPath;
      final file = File(filePath);
      if (!await file.exists()) return MissReviewHear.missed;
      final bytes = await file.readAsBytes();
      if (bytes.isEmpty) return MissReviewHear.missed;
      final heard = await widget.client
          .recognizePracticeTake(bytes: bytes, mime: 'audio/mp4')
          .timeout(kMissReviewSttWait);
      if (!_reviewAlive(token)) return MissReviewHear.skip;
      // The chunk already holds this word's spoken form and phones, so the
      // review does not ask the server for one word.
      final chunkDisplay = _displayChunk();
      final targetPhone = _skill.spokenCache.phonesForWordIn(
        sentence: chunkDisplay,
        word: word,
      );
      final trace = traceMissReview(expected: word, heard: heard);
      final heardPhone = widget.client.lastHeardPhones;
      final drill = trace.matched
          ? const <String>[]
          : phoneDrillTargets(target: targetPhone, heard: heardPhone);
      if (mounted) {
        setState(() {
          _reviewTargetPhone = targetPhone;
          _reviewHeardPhone = heardPhone;
          _reviewDrillPhones = drill;
        });
      }
      await _skill.noteMissReview(
        expected: word,
        heard: heard,
        matched: trace.matched,
        pieces: trace.pieces,
        hits: trace.hits,
        attempt: attempt,
        wordIndex: wordIndex,
        drillPhones: drill.join(' '),
      );
      if (trace.matched) {
        return MissReviewHear.matched;
      }
      return MissReviewHear.missed;
    } catch (_) {
      return MissReviewHear.missed;
    } finally {
      if (started) {
        unawaited(_mic.invokeMethod<String>('stop'));
      }
    }
  }

  Future<void> _runBlankRest({
    required int token,
    required int chunkCountN,
    required int step1Based,
  }) async {
    final dur = blankRestDuration(
      chunkCountN: chunkCountN,
      step1Based: step1Based,
    );
    if (dur <= Duration.zero) return;
    if (!mounted || token != _cycleToken) return;
    if (!_focus.sessionActive || _focus.paused) return;
    final epoch = ++_restEpoch;
    _armRestWatchdog(
      token: token,
      epoch: epoch,
      limit: restCoverWatchdogLimit(scheduledRest: dur),
    );
    setState(() => _rhythmPhase = RhythmPhase.rest);
    final still = await _awaitRestDeadline(
      token: token,
      epoch: epoch,
      deadline: DateTime.now().add(dur),
    );
    if (!still) {
      if (epoch == _restEpoch) _clearRestWatchdog();
      if (mounted &&
          epoch == _restEpoch &&
          _rhythmPhase == RhythmPhase.rest) {
        setState(() => _rhythmPhase = RhythmPhase.idle);
      }
      return;
    }
    _clearRestWatchdog();
    if (mounted && _rhythmPhase == RhythmPhase.rest) {
      setState(() => _rhythmPhase = RhythmPhase.idle);
    }
  }

  Future<void> _advanceToNextChunk({
    required int token,
    bool withRest = true,
    List<String> reviewWords = const [],
  }) async {
    if (!mounted || token != _cycleToken) return;
    final session = _session;
    if (session == null) return;

    final restN = _chunks.length;
    final restK = _chunkIndex + 1;
    final words = withRest ? reviewWords : const <String>[];
    final scheduledRest = withRest && _blankRestEnabled
        ? blankRestDuration(chunkCountN: restN, step1Based: restK)
        : Duration.zero;
    final reviewTier = missReviewTier(_heardSkillTier);
    final reviewRandom = _heardRandomAuto;
    final reviewVoice = _heardVoice;
    final reviewRate = _heardClientRate;

    Future<bool> reviewOnce() async {
      if (words.isEmpty) return true;
      await _runMissReview(
        token: token,
        words: words,
        scheduledRest: scheduledRest,
        reviewTier: reviewTier,
        randomAuto: reviewRandom,
        voice: reviewVoice,
        clientRate: reviewRate,
      );
      if (!mounted || token != _cycleToken) return false;
      if (!_focus.sessionActive || _focus.paused) return false;
      return true;
    }

    _lastTakePath = null;
    _clearChunkTtsCache();
    var canContinue = false;
    String? prevSection;
    var maybeSectionChange = false;

    if (_chunkIndex + 1 < _chunks.length) {
      _chunkIndex += 1;
      unawaited(_persistPracticeCursor());
      canContinue = true;
    } else if (_sentenceIndex + 1 < session.sentenceCount) {
      prevSection = _sectionKeyFor(session);
      maybeSectionChange = true;
      final rows = <({String id, String text})>[
        for (final s in session.sentences) (id: s.id, text: s.text),
      ];
      final delta = shadowingSkipEmptyDelta(
        plan: _plan,
        sentences: rows,
        fromIndex: _sentenceIndex + 1,
      );
      if (delta < 0) {
        final ensureBusy = widget.library.shadowingChunksBusy;
        final pending = shadowingPlanStatusIsPending(_plan) ||
            (!shadowingPlanStatusIsOk(_plan) && ensureBusy);
        if (pending || ensureBusy) {
          await _mergeLatestPlan();
          final again = shadowingSkipEmptyDelta(
            plan: _plan,
            sentences: rows,
            fromIndex: _sentenceIndex + 1,
          );
          if (again >= 0) {
            _bindSentenceAt(session, _sentenceIndex + 1 + again);
            canContinue = _chunks.isNotEmpty;
          } else {
            setState(() => _status = '다음 문장 준비 중…');
            if (!await reviewOnce()) return;
            if (mounted && _rhythmPhase == RhythmPhase.rest) {
              setState(() => _rhythmPhase = RhythmPhase.idle);
            }
            return;
          }
        } else {
          setState(() => _status = '이 논문 연습을 끝까지 돌았습니다.');
          if (!await reviewOnce()) return;
          if (mounted && _rhythmPhase == RhythmPhase.rest) {
            setState(() => _rhythmPhase = RhythmPhase.idle);
          }
          return;
        }
      } else {
        _bindSentenceAt(session, _sentenceIndex + 1 + delta);
        canContinue = _chunks.isNotEmpty;
      }
      if (!canContinue) {
        final ensureBusy = widget.library.shadowingChunksBusy;
        if (ensureBusy || shadowingPlanStatusIsPending(_plan)) {
          setState(() => _status = '다음 문장 준비 중…');
        } else {
          setState(() => _status = '이 논문 연습을 끝까지 돌았습니다.');
        }
        // Still show section cue if we landed on empty next section.
        if (maybeSectionChange && mounted && token == _cycleToken) {
          final next = _session ?? session;
          await _showSectionCueIfChanged(
            previousKey: prevSection,
            session: next,
            token: token,
          );
        }
        if (!await reviewOnce()) return;
        if (mounted && _rhythmPhase == RhythmPhase.rest) {
          setState(() => _rhythmPhase = RhythmPhase.idle);
        }
        return;
      }
    } else {
      setState(() => _status = '이 논문 연습을 끝까지 돌았습니다.');
      if (!await reviewOnce()) return;
      if (mounted && _rhythmPhase == RhythmPhase.rest) {
        setState(() => _rhythmPhase = RhythmPhase.idle);
      }
      return;
    }
    if (!mounted || token != _cycleToken) return;

    // After cursor move — rematch for next Listen (design/274).
    _flushPendingDensityRematch();

    if (maybeSectionChange) {
      final next = _session ?? session;
      await _showSectionCueIfChanged(
        previousKey: prevSection,
        session: next,
        token: token,
      );
      if (!mounted || token != _cycleToken) return;
    }

    if (words.isNotEmpty) {
      if (!await reviewOnce()) return;
    } else if (withRest && _blankRestEnabled && canContinue) {
      await _runBlankRest(
        token: token,
        chunkCountN: restN,
        step1Based: restK,
      );
      if (!mounted || token != _cycleToken) return;
      if (!_focus.sessionActive || _focus.paused) return;
    }

    await _runCycle();
  }

  void _toggleMirror() {
    setState(() => _mirrorEnabled = !_mirrorEnabled);
  }

  void _onGiveUp() {
    _cycleToken++;
    _restEpoch++;
    _clearRestWatchdog();
    unawaited(_player.stop());
    _clearFollowLight();
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
          '집중 종료 · 미완료 ${kFocusPracticeBlockDuration.inMinutes}분은 초기화됩니다. 「시작」으로 다시.';
      _rhythmPhase = RhythmPhase.idle;
      _judgmentBurst = null;
      _sectionCueName = null;
      _reviewWord = null;
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
    unawaited(_loadBlankRestPref());
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
    _restEpoch++;
    _clearRestWatchdog();
    unawaited(_player.stop());
    _clearFollowLight();
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
      await _showSectionCueIfChanged(
        previousKey: prevSection,
        session: session,
        token: _cycleToken,
      );
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
                        if (_practiceReady &&
                            _focus.sessionActive &&
                            _rhythmPhase != RhythmPhase.rest &&
                            _sectionCueName == null) ...[
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
                            child: LayoutBuilder(
                              builder: (context, constraints) {
                                _promptMaxWidth = constraints.maxWidth;
                                final showFollow =
                                    _rhythmPhase == RhythmPhase.listen ||
                                        _rhythmPhase == RhythmPhase.speak;
                                return SingleChildScrollView(
                                  controller: _promptScroll,
                                  child: WordPhoneText(
                                    text: prompt.isEmpty ? '…' : prompt,
                                    spans: _skill.spokenCache.peekSpans(prompt),
                                    style: _promptStyle(theme),
                                    misses: _replayMissChunk == _chunkIndex
                                        ? _replayMisses
                                        : const [],
                                    follow: showFollow ? _follow : null,
                                    markAlpha:
                                        _rhythmPhase == RhythmPhase.replay
                                            ? 1.0
                                            : 0.0,
                                  ),
                                );
                              },
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
                              : '${kFocusPracticeBlockDuration.inMinutes}분 말하기 · 남은 $missionLeft',
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
                    if (_sectionCueName != null ||
                        _rhythmPhase == RhythmPhase.rest)
                      Positioned(
                        left: 0,
                        right: 0,
                        top: 0,
                        // Leave 「집중 끝내기」 tappable (design/274).
                        bottom: 64,
                        child: IgnorePointer(
                          child: ColoredBox(
                            color: kRhythmStage,
                            child: _sectionCueName != null
                                ? Center(
                                    child: Padding(
                                      padding: const EdgeInsets.symmetric(
                                        horizontal: 28,
                                      ),
                                      child: Text(
                                        _sectionCueName!,
                                        textAlign: TextAlign.center,
                                        style: theme.textTheme.headlineMedium
                                            ?.copyWith(
                                          color: kRhythmText,
                                          fontWeight: FontWeight.w600,
                                          height: 1.25,
                                        ),
                                      ),
                                    ),
                                  )
                                : _reviewWord == null
                                    ? const SizedBox.expand()
                                    : Center(
                                        child: Padding(
                                          padding: const EdgeInsets.symmetric(
                                            horizontal: 28,
                                          ),
                                          child: Column(
                                            mainAxisSize: MainAxisSize.min,
                                            children: [
                                              Text(
                                                _reviewWord!,
                                                textAlign: TextAlign.center,
                                                style: theme
                                                    .textTheme.headlineMedium
                                                    ?.copyWith(
                                                  color: kRhythmText,
                                                  fontWeight: FontWeight.w600,
                                                  height: 1.25,
                                                ),
                                              ),
                                              if (_reviewDrillPhones.isNotEmpty)
                                                Padding(
                                                  padding:
                                                      const EdgeInsets.only(
                                                    top: 10,
                                                  ),
                                                  child: Text(
                                                    'This sound  ${_reviewDrillPhones.join('  ')}',
                                                    textAlign:
                                                        TextAlign.center,
                                                    style: theme
                                                        .textTheme.titleMedium
                                                        ?.copyWith(
                                                      color: kRhythmSpeak,
                                                      fontWeight:
                                                          FontWeight.w600,
                                                    ),
                                                  ),
                                                ),
                                              if (_reviewTargetPhone.isNotEmpty)
                                                Text(
                                                  'You can also say  $_reviewTargetPhone',
                                                  textAlign: TextAlign.center,
                                                  style: theme
                                                      .textTheme.bodyMedium
                                                      ?.copyWith(
                                                    color: kRhythmText,
                                                  ),
                                                ),
                                              if (_reviewHeardPhone.isNotEmpty)
                                                Text(
                                                  'It came out  $_reviewHeardPhone',
                                                  textAlign: TextAlign.center,
                                                  style: theme
                                                      .textTheme.bodyMedium
                                                      ?.copyWith(
                                                    color: kRhythmText
                                                        .withValues(alpha: 0.75),
                                                  ),
                                                ),
                                            ],
                                          ),
                                        ),
                                      ),
                          ),
                        ),
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
    this.score,
  });

  final bool ok;
  final GroomingSignal signal;
  final String code;
  final int wallMs;
  final int takeBytes;
  final int takeDurMs;
  final bool persistOk;
  final bool cloudTakeOk;
  final Future<({String display, List<MissedWordSpan> spans})?>? score;
}
