/// Paper library + opened reading session (design/62 · 70 · 71 · 72 · 74 · 75 · 76).
library;

import 'dart:async';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/client.dart';
import '../api/ingest_models.dart';
import '../api/paper_models.dart';
import '../api/progress_gate.dart';
import '../api/progress_store.dart';
import '../api/reading_models.dart';
import '../api/upload_draft_models.dart';
import '../api/upload_draft_store.dart';
import '../api/upload_notify.dart';
import '../api/shadowing_models.dart';
import '../api/translate_models.dart';
import '../api/library_order_models.dart';
import '../api/bookmark_models.dart';
import '../state/bookmark_controller.dart';
import '../state/annotation_controller.dart';
import '../services/error_reporter.dart';
import '../services/hang_watchdog.dart';
import '../services/paper_edit_stash.dart';

/// Stall after this long without progress while an upload is marked active.
const Duration kUploadStallAfter = Duration(seconds: 45);

/// Loads `/api/cache/papers`, opens a cache entry, advances cursors independently.
class LibraryController extends ChangeNotifier {
  LibraryController({
    required AsrClient client,
    UploadDraftStore? draftStore,
    UploadNotify? uploadNotify,
    PaperEditStash? editStash,
  })  : _client = client,
        _drafts = draftStore ?? PrefsUploadDraftStore(),
        _notify = uploadNotify ?? createUploadNotify(),
        _editStash = editStash ?? PaperEditStash();

  final AsrClient _client;
  final UploadDraftStore _drafts;
  final UploadNotify _notify;
  final PaperEditStash _editStash;

  PaperEditStash get editStash => _editStash;
  BookmarkController? _bookmarks;
  AnnotationController? _annotations;

  void attachBookmarks(BookmarkController bookmarks) {
    _bookmarks = bookmarks;
    bookmarks.attachClient(_client);
  }

  void attachAnnotations(AnnotationController annotations) {
    _annotations = annotations;
    annotations.attachClient(_client);
  }

  List<PaperEntry> papers = const [];
  ReadingSession? session;
  bool loading = false;
  bool opening = false;
  bool uploading = false;
  /// design/145 — reanalyze job in flight (separate from upload cancel/draft path).
  bool reanalyzing = false;
  String? reanalyzingCacheId;
  int uploadPercent = 0;
  String uploadStage = '';
  String? error;
  /// design/80 — fail-closed banner when chunk plan missing/failed.
  String? shadowingChunksError;
  String? shadowingChunksCacheId;
  bool shadowingChunksBusy = false;

  /// design/99 — KO backfill polling after /open (translate_pending).
  bool translateBackfillBusy = false;
  Timer? _translatePollTimer;

  /// design/167 — show ingest quality banner once per open until dismissed.
  bool showIngestQualityBanner = false;
  String? _dismissedQualityBannerCacheId;

  /// design/160 — uid-scoped read-left timestamps for library meta lines.
  Map<String, String> readLeftAtByCacheId = const {};

  /// design/74 — set when notification permission blocked but upload continues.
  String? uploadBackgroundHint;

  /// design/76 — battery restrict guidance (button); null when not applicable.
  String? uploadBatteryHint;

  /// Content hash for the in-flight upload (battery dismiss scope).
  String? _activeContentHash;

  /// design/75 — true when progress heartbeat went silent (honest interrupt UI).
  bool uploadStalled = false;

  /// design/158 — show 「이어서 분석하기」 when a resumable draft exists.
  bool resumeOfferVisible = false;

  /// design/132 — user asked to cancel the in-flight upload/ingest.
  bool _uploadCancelRequested = false;
  String? _activeUploadId;
  String? _activeJobId;

  /// design/134 — hang watchdog op for current upload attempt (stable per try).
  String? _hangOpId;
  bool _ingestHangTripped = false;
  bool _hangLocalBound = false;
  int _hangLastPercent = -1;
  String _hangLastStageKey = '';

  DateTime? _lastProgressAt;
  Timer? _stallWatch;
  bool _resumeInFlight = false;
  /// Cached for one upload session — avoid /api/status on every chunk heartbeat.
  bool? _wmEnabledCache;
  DateTime? _lastWmScheduleAt;

  ReadingSession? get opened => session;

  UploadNotify get uploadNotify => _notify;

  Future<void> initUploadNotify() => _notify.init();

  /// design/74 — honor server kill switch; on status failure skip FG only.
  Future<bool> _backgroundNotifyEnabled() async {
    try {
      final st = await _client.fetchStatus();
      return st.mobileUploadBackground;
    } catch (_) {
      // WHY: notify is optional; upload must still proceed fail-closed for FG.
      return false;
    }
  }

  Future<bool> _interruptResumeEnabled() async {
    try {
      final st = await _client.fetchStatus();
      return st.mobileUploadInterruptResume;
    } catch (_) {
      // EDGE: status down → skip aggressive resume; cold 71 path still works.
      return false;
    }
  }

  Future<bool> _workmanagerEnabled() async {
    final cached = _wmEnabledCache;
    if (cached != null) return cached;
    try {
      final st = await _client.fetchStatus();
      _wmEnabledCache = st.mobileUploadWorkmanager;
    } catch (_) {
      // EDGE: status down → do not enqueue WM (fail closed for new surface).
      _wmEnabledCache = false;
    }
    return _wmEnabledCache!;
  }

  Future<UploadNotifyStart> _maybeStartNotify(String stage) async {
    if (!await _backgroundNotifyEnabled()) {
      return const UploadNotifyStart(active: false);
    }
    return _notify.startUploading(stage: stage);
  }

  /// design/76 — REPLACE + delay so live Flutter progress resets the death timer.
  Future<void> _scheduleWorkmanager({required bool immediate}) async {
    if (!await _workmanagerEnabled()) return;
    if (!immediate) {
      final last = _lastWmScheduleAt;
      // WHY: throttle channel spam — chunk heartbeats are frequent.
      if (last != null &&
          DateTime.now().difference(last) < const Duration(seconds: 20)) {
        return;
      }
    }
    _lastWmScheduleAt = DateTime.now();
    await _notify.scheduleUploadResume(immediate: immediate);
  }

  Future<void> _cancelWorkmanager() async {
    _lastWmScheduleAt = null;
    await _notify.cancelUploadResume();
  }

  /// Progress heartbeat also postpones WM so a live Dart upload is not raced.
  void _touchProgress() {
    _lastProgressAt = DateTime.now();
    if (uploadStalled) {
      uploadStalled = false;
    }
    // WHY: resets the ~60s REPLACE delay — WM only fires if frozen/dead.
    unawaited(_scheduleWorkmanager(immediate: false));
  }

  /// design/134 — map UI stage text to coarse forward keys (label flicker ≠ progress).
  String _hangStageKey(String stage) {
    final s = stage.trim().toLowerCase();
    if (s.contains('처리') || s.contains('process') || s.contains('정제')) {
      return 'processing';
    }
    if (s.contains('조각') || s.contains('upload') || s.contains('올리')) {
      return 'uploading';
    }
    if (s.contains('이어')) return 'reattach';
    if (s.contains('준비')) return 'prepare';
    if (s.isEmpty) return 'ingest';
    return s.length > 24 ? s.substring(0, 24) : s;
  }

  bool _hangStageForward(String next, String prev) {
    const order = ['prepare', 'uploading', 'reattach', 'processing', 'done'];
    final a = order.indexOf(prev);
    final b = order.indexOf(next);
    if (a >= 0 && b >= 0) return b > a;
    return next.isNotEmpty && next != prev;
  }

  void _ensureHangLocalBound() {
    if (_hangLocalBound) return;
    _hangLocalBound = true;
    asrErrorReporter?.hang.setLocalHandler(_onIngestHangLocal);
  }

  /// design/134 — local fail-closed abort; cloud report runs after via HangWatchdog.
  void _onIngestHangLocal(String opId, String kind) {
    if (_hangOpId == null || opId != _hangOpId) return;
    // WHY: stop poll/chunk loops; do not call server cancel API this chip.
    _uploadCancelRequested = true;
    _ingestHangTripped = true;
    error = '응답이 없어 업로드를 중단했습니다. 다시 시도해 주세요.';
    uploadStage = '중단됨';
    uploadStalled = false;
    notifyListeners();
    unawaited(_notify.showFailed(message: error!));
    unawaited(_refreshResumeOffer());
  }

  Future<bool> _draftResumable() async {
    final draft = await _drafts.read();
    if (draft == null) return false;
    return draft.canReattach || draft.canResumeChunks;
  }

  Future<void> _refreshResumeOffer() async {
    resumeOfferVisible = !uploading && !reanalyzing && await _draftResumable();
    notifyListeners();
  }

  Future<void> _beginIngestHang({required String filename}) async {
    _ensureHangLocalBound();
    _endIngestHang();
    _ingestHangTripped = false;
    _hangLastPercent = -1;
    _hangLastStageKey = '';
    var enabled = true;
    var stall = HangWatchdog.ingestStall;
    try {
      final st = await _client.fetchStatus();
      enabled = st.mobileIngestUploadHang;
      if (st.ingestHangStallSeconds > 0) {
        stall = Duration(seconds: st.ingestHangStallSeconds);
      }
    } catch (_) {
      // EDGE: status fail → keep hang on with default 3m (fail-closed for zombies).
      enabled = true;
      stall = HangWatchdog.ingestStall;
    }
    if (!enabled) return;
    final opId =
        'ingest_${DateTime.now().millisecondsSinceEpoch}_${filename.hashCode}';
    _hangOpId = opId;
    asrErrorReporter?.hang.begin(
      opId,
      stage: 'ingest_upload',
      stallAfter: stall,
      paperTitle: filename.trim().isEmpty ? null : filename.trim(),
    );
  }

  /// Only real forward progress resets the hang clock (design/134 product 2).
  void _noteIngestHangProgress({required int percent, required String stage}) {
    final op = _hangOpId;
    if (op == null) return;
    final key = _hangStageKey(stage);
    final pct = percent.clamp(0, 100);
    final pctUp = pct > _hangLastPercent;
    final stageUp = _hangStageForward(key, _hangLastStageKey);
    if (!pctUp && !stageUp) {
      // Same place — leave stall timer running (do not noteRepeat every poll).
      return;
    }
    _hangLastPercent = pct;
    if (stageUp || _hangLastStageKey.isEmpty) {
      _hangLastStageKey = key;
    }
    asrErrorReporter?.hang.progress(op, stage: key);
    // design/168d A1.11 — breadcrumb only on real progress (not every 500ms poll).
    unawaited(
      asrErrorReporter?.report(
            kind: 'ingest_poll_breadcrumb',
            message: 'pct=$pct stage=$key',
            stage: key,
          ) ??
          Future<void>.value(),
    );
  }

  void _endIngestHang() {
    final op = _hangOpId;
    if (op != null) {
      asrErrorReporter?.hang.end(op);
    }
    _hangOpId = null;
  }

  Future<void> _maybeOfferBatteryHint(String contentHash) async {
    final hash = contentHash.trim().toLowerCase();
    if (hash.isEmpty) return;
    if (await _notify.isIgnoringBatteryOptimizations()) {
      uploadBatteryHint = null;
      return;
    }
    final p = await SharedPreferences.getInstance();
    final dismissed = (p.getString(kBatteryHintDismissedHashKey) ?? '')
        .trim()
        .toLowerCase();
    if (dismissed == hash) {
      // Product 3: same content_hash job — user already dismissed; do not re-nag.
      uploadBatteryHint = null;
      return;
    }
    uploadBatteryHint =
        '업로드 중 앱을 나가도 이어올리려면 배터리 제한을 해제해야 합니다. '
        '아래 버튼을 누르면 「허용」을 선택해 주세요.';
  }

  /// UI: open per-app battery exemption (design/76).
  Future<bool> openBatterySettings() async {
    final ok = await _notify.openBatterySettings();
    final hash = (_activeContentHash ?? '').trim().toLowerCase();
    if (hash.isNotEmpty) {
      await _maybeOfferBatteryHint(hash);
      notifyListeners();
    }
    return ok;
  }

  /// UI: dismiss battery guidance for this content_hash only.
  Future<void> dismissBatteryHint() async {
    final hash = (_activeContentHash ?? '').trim().toLowerCase();
    if (hash.isNotEmpty) {
      final p = await SharedPreferences.getInstance();
      await p.setString(kBatteryHintDismissedHashKey, hash);
    }
    uploadBatteryHint = null;
    notifyListeners();
  }

  void _startStallWatch() {
    _stallWatch?.cancel();
    _lastProgressAt = DateTime.now();
    uploadStalled = false;
    // WHY: periodic check — phone/OEM may freeze Dart without a lifecycle event.
    _stallWatch = Timer.periodic(const Duration(seconds: 15), (_) {
      unawaited(_checkStall());
    });
  }

  void _stopStallWatch() {
    _stallWatch?.cancel();
    _stallWatch = null;
    uploadStalled = false;
    _lastProgressAt = null;
  }

  Future<void> _checkStall() async {
    if (!uploading) return;
    if (!await _interruptResumeEnabled()) return;
    final last = _lastProgressAt;
    if (last == null) return;
    if (DateTime.now().difference(last) < kUploadStallAfter) return;
    if (uploadStalled) return;
    // Fail-closed honesty: do not keep a fake “still uploading” story.
    uploadStalled = true;
    uploadStage = '중단됨 · 앱을 열면 이어갑니다';
    notifyListeners();
    await _notify.showInterrupted(stage: uploadStage);
    // design/76: stall → REPLACE immediate WorkManager (process may already be dying).
    await _scheduleWorkmanager(immediate: true);
  }

  /// design/75 — call from HomeShell on AppLifecycleState.resumed.
  Future<IngestJobResult?> onAppResumed() async {
    if (_resumeInFlight) return null;
    if (!await _interruptResumeEnabled()) return null;
    final draft = await _drafts.read();
    if (draft == null) return null;

    if (uploading) {
      final last = _lastProgressAt;
      final stale = last == null ||
          DateTime.now().difference(last) >= kUploadStallAfter ||
          uploadStalled;
      if (!stale) {
        // Still receiving progress — do not start a second upload.
        return null;
      }
      // WHY: frozen in-flight Future may never clear `uploading`; release lock
      // so design/71 resume can reattach. Server job poll is idempotent.
      uploading = false;
      _stopStallWatch();
      notifyListeners();
    }

    _resumeInFlight = true;
    try {
      return await resumePendingIfAny();
    } finally {
      _resumeInFlight = false;
    }
  }

  Future<void> refresh() async {
    loading = true;
    error = null;
    notifyListeners();
    try {
      final fetched = await _client.listPapers();
      papers = await _applySavedOrder(fetched);
    } on AsrApiException catch (e) {
      error = e.message;
      papers = const [];
    } on TimeoutException catch (_) {
      // design/159 — keep last good list; server may still complete after app gave up.
      error = '서버 응답이 느립니다. 잠시 후 새로고침해 주세요.';
    } catch (e) {
      error = e.toString();
      papers = const [];
    } finally {
      loading = false;
      notifyListeners();
      unawaited(_refreshResumeOffer());
      unawaited(refreshReadLeftTimes());
      unawaited(
        _editStash.purgeOrphans(papers.map((p) => p.id).toSet()),
      );
    }
  }

  /// design/160 — load read-left timestamps for current paper list.
  Future<void> refreshReadLeftTimes() async {
    if (papers.isEmpty) {
      readLeftAtByCacheId = const {};
      notifyListeners();
      return;
    }
    try {
      final uid = await _authUid();
      readLeftAtByCacheId = await loadReadLeftAtForPapers(
        uid: uid,
        cacheIds: papers.map((p) => p.id),
      );
      notifyListeners();
    } catch (_) {
      // EDGE: prefs fail — keep last map.
    }
  }

  /// design/160 — record when user leaves reading tab or backgrounds app.
  Future<void> recordReadLeft() async {
    final s = session;
    if (s == null || !s.isValid || s.cacheId.isEmpty) return;
    try {
      final uid = await _authUid();
      await recordReadLeftAt(uid: uid, cacheId: s.cacheId);
      final at = await loadLastReadLeftAt(uid: uid, cacheId: s.cacheId);
      if (at != null) {
        readLeftAtByCacheId = {
          ...readLeftAtByCacheId,
          s.cacheId: at,
        };
        notifyListeners();
      }
    } catch (_) {
      // EDGE: prefs fail must not block navigation.
    }
  }

  /// design/101 — long-press drag reorder; persist uid-scoped prefs.
  Future<void> reorderPapers(int oldIndex, int newIndex) async {
    if (oldIndex < 0 || oldIndex >= papers.length) return;
    var dest = newIndex;
    if (dest > oldIndex) dest -= 1;
    if (dest < 0 || dest >= papers.length) return;
    if (oldIndex == dest) return;
    final next = List<PaperEntry>.from(papers);
    final item = next.removeAt(oldIndex);
    next.insert(dest, item);
    papers = next;
    notifyListeners();
    await _persistOrder(next.map((e) => e.id).toList(growable: false));
  }

  /// design/102 — delete selected papers (GCS + user records via API).
  Future<int> deletePapers(Iterable<String> cacheIds) async {
    final ids = cacheIds
        .map((e) => e.trim())
        .where((e) => e.isNotEmpty)
        .toSet()
        .toList(growable: false);
    if (ids.isEmpty) return 0;
    var okCount = 0;
    String? lastErr;
    for (final id in ids) {
      try {
        await _client.deletePaper(id);
        okCount += 1;
        await _editStash.purge(id);
        await _bookmarks?.purgePaper(id);
        if (session?.cacheId == id) {
          clearOpened();
        }
      } on AsrApiException catch (e) {
        lastErr = e.message;
      } catch (e) {
        lastErr = e.toString();
      }
    }
    papers = papers.where((p) => !ids.contains(p.id)).toList(growable: false);
    await _persistOrder(papers.map((e) => e.id).toList(growable: false));
    error = okCount == 0 ? (lastErr ?? '삭제에 실패했습니다.') : null;
    notifyListeners();
    return okCount;
  }

  /// design/144 — extend retention +90d when server allows.
  Future<bool> extendRetention(PaperEntry entry) async {
    if (!entry.retentionCanExtend) return false;
    try {
      await _client.extendPaperRetention(entry.id);
      await refresh();
      error = null;
      notifyListeners();
      return true;
    } on AsrApiException catch (e) {
      error = e.message;
      notifyListeners();
      return false;
    } catch (e) {
      error = e.toString();
      notifyListeners();
      return false;
    }
  }

  /// design/145 — reanalyze from stored source (web parity); no confirm dialog.
  Future<bool> reanalyzePaper(PaperEntry entry) async {
    if (!entry.hasSource) return false;
    // WHY: one heavy job at a time — fail-closed, no overlapping ingest.
    if (uploading || reanalyzing || opening) {
      error = '다른 작업 중입니다. 잠시 후 다시 시도해 주세요.';
      notifyListeners();
      return false;
    }
    reanalyzing = true;
    reanalyzingCacheId = entry.id;
    uploadPercent = 0;
    uploadStage = '재분석 시작';
    error = null;
    notifyListeners();
    try {
      final wantTr = await _wantTranslate();
      final started = await _client.startReanalyze(
        entry.id,
        translate: wantTr,
      );
      final result = await _client.pollIngestJob(
        jobId: started.jobId,
        onProgress: (pct, msg) {
          uploadPercent = pct.clamp(0, 100);
          uploadStage = msg.isEmpty ? '재분석 중' : msg;
          notifyListeners();
        },
      );
      await refresh();
      if (result.cacheId.isEmpty) {
        error = '재분석은 끝났지만 보관함에 반영되지 않았습니다.';
        notifyListeners();
        return false;
      }
      final seen = papers.any((p) => p.id == result.cacheId);
      if (!seen) {
        error = '재분석은 끝났지만 목록에 아직 없습니다. 새로고침해 주세요.';
        notifyListeners();
        return false;
      }
      // WHY: 재분석 후 읽기 탭에 옛 session이 남지 않게 최신 /open 반영.
      if (session?.cacheId == entry.id) {
        await open(entry);
      }
      await _editStash.invalidatePreviews(entry.id);
      error = null;
      notifyListeners();
      return true;
    } on AsrApiException catch (e) {
      error = e.message;
      notifyListeners();
      return false;
    } catch (e) {
      error = e.toString();
      notifyListeners();
      return false;
    } finally {
      reanalyzing = false;
      reanalyzingCacheId = null;
      uploadPercent = 0;
      uploadStage = '';
      notifyListeners();
    }
  }

  /// design/152 — merge paired supplementary into main session.
  Future<bool> mergeSupplementary(PaperEntry entry) async {
    if (!entry.canMergeSupplementary) return false;
    if (uploading || reanalyzing || opening) {
      error = '다른 작업 중입니다. 잠시 후 다시 시도해 주세요.';
      notifyListeners();
      return false;
    }
    opening = true;
    error = null;
    notifyListeners();
    try {
      await _client.mergeSupplementary(entry.id);
      await refresh();
      error = null;
      notifyListeners();
      return true;
    } on AsrApiException catch (e) {
      error = e.message;
      notifyListeners();
      return false;
    } catch (e) {
      error = e.toString();
      notifyListeners();
      return false;
    } finally {
      opening = false;
      notifyListeners();
    }
  }

  Future<List<PaperEntry>> _applySavedOrder(List<PaperEntry> fetched) async {
    try {
      final auth = await _client.fetchAuthStatus();
      final uid = auth.user?.uid;
      if (uid == null || uid.isEmpty) return fetched;
      final p = await SharedPreferences.getInstance();
      final order = parseLibraryOrderPref(p.getString(libraryOrderPrefsKey(uid)));
      return applyLibraryOrder(
        papers: fetched,
        orderIds: order,
        idOf: (e) => e.id,
      );
    } catch (_) {
      return fetched;
    }
  }

  Future<void> _persistOrder(List<String> ids) async {
    try {
      final auth = await _client.fetchAuthStatus();
      final uid = auth.user?.uid;
      if (uid == null || uid.isEmpty) return;
      final p = await SharedPreferences.getInstance();
      await p.setString(
        libraryOrderPrefsKey(uid),
        serializeLibraryOrderPref(ids),
      );
    } catch (_) {
      // EDGE: prefs fail → in-memory order still shown until next refresh.
    }
  }

  /// design/123 — kill switch from /api/status (missing key → fail-closed).
  Future<bool> _progressFailClosed() async {
    try {
      final st = await _client.fetchStatus();
      return st.progressFailClosed;
    } catch (_) {
      // EDGE: status down → refuse bad progress (safer than silent clamp).
      return true;
    }
  }

  Future<String?> _authUid() async {
    try {
      final auth = await _client.fetchAuthStatus();
      final uid = auth.user?.uid;
      if (uid == null || uid.isEmpty) return null;
      return uid;
    } catch (_) {
      return null;
    }
  }

  /// Persist opened cursors to uid-scoped prefs (design/123 product 5C).
  Future<void> persistOpenedProgress() async {
    final s = session;
    if (s == null || !s.isValid || s.cacheId.isEmpty) return;
    try {
      final uid = await _authUid();
      await saveProgressRow(
        uid: uid,
        cacheId: s.cacheId,
        sentenceIndex: s.sentenceIndex,
        figureIndex: s.figureIndex,
      );
    } catch (_) {
      // EDGE: prefs fail must not block reading UI.
    }
  }

  Future<void> _syncBookmarksForSession(ReadingSession o) async {
    final bm = _bookmarks;
    if (bm == null) return;
    await bm.loadPaper(o.cacheId);
    await bm.applyNavPrune(
      sectionNav: o.sectionNav,
      figureNav: o.figureNav,
    );
    unawaited(bm.pullFromServer());
  }

  Future<void> _syncAnnotationsForSession(ReadingSession o) async {
    final ann = _annotations;
    if (ann == null) return;
    await ann.loadPaper(o.cacheId);
    await ann.applyNavPrune(
      sectionNav: o.sectionNav,
      figureNav: o.figureNav,
    );
    await ann.reanchorToSession(o);
    unawaited(ann.pullFromServer());
  }

  bool _sessionNeedsQualityBanner(ReadingSession o) {
    final iq = o.ingestQuality;
    if (iq != null && iq.needsBanner(o.warnings)) return true;
    return o.warnings.any((w) =>
        w.startsWith('coverage_') ||
        w.startsWith('partial_debone') ||
        w.startsWith('chunk_fallback_split') ||
        w.startsWith('ungrounded_sentences') ||
        w.startsWith('high_body_ratio') ||
        w == 'stale_pipeline');
  }

  void _maybeShowQualityBanner(ReadingSession o) {
    if (_sessionNeedsQualityBanner(o) &&
        o.cacheId != _dismissedQualityBannerCacheId) {
      showIngestQualityBanner = true;
    } else {
      showIngestQualityBanner = false;
    }
  }

  void dismissIngestQualityBanner() {
    showIngestQualityBanner = false;
    final cid = session?.cacheId;
    if (cid != null && cid.isNotEmpty) {
      _dismissedQualityBannerCacheId = cid;
    }
    notifyListeners();
  }

  void _stopTranslatePoll() {
    _translatePollTimer?.cancel();
    _translatePollTimer = null;
    if (translateBackfillBusy) {
      translateBackfillBusy = false;
      notifyListeners();
    }
  }

  void _maybeStartTranslatePoll(ReadingSession o) {
    _stopTranslatePoll();
    if (!o.translatePending && o.hasAnyTranslation) return;
    unawaited(_wantTranslate().then((wantTr) {
      if (!wantTr) return;
      if (!o.translatePending && o.hasAnyTranslation) return;
      if (session?.cacheId != o.cacheId) return;
      translateBackfillBusy = true;
      notifyListeners();
      var attempts = 0;
      var pollErrorReported = false;
      _translatePollTimer?.cancel();
      _translatePollTimer = Timer.periodic(const Duration(seconds: 8), (t) async {
        attempts++;
        if (attempts > 24) {
          // design/168d D1.14 — exhausted is not success; report once.
          unawaited(
            asrErrorReporter?.report(
                  kind: 'translate_poll_exhausted',
                  message: 'open translate poll stopped after 24 attempts',
                  stage: 'translate_poll',
                  cacheId: o.cacheId,
                ) ??
                Future<void>.value(),
          );
          _stopTranslatePoll();
          return;
        }
        final cid = session?.cacheId;
        if (cid == null || cid != o.cacheId) {
          _stopTranslatePoll();
          return;
        }
        try {
          final wantTr2 = await _wantTranslate();
          if (!wantTr2) {
            _stopTranslatePoll();
            return;
          }
          final refreshed = await _client.openPaper(cid, translate: true);
          if (session?.cacheId != cid) return;
          final si = session!.sentenceIndex;
          final fi = session!.figureIndex;
          refreshed.sentenceIndex = si;
          refreshed.figureIndex = fi;
          refreshed.clampIndices();
          session = refreshed;
          if (!refreshed.translatePending && refreshed.hasAnyTranslation) {
            _stopTranslatePoll();
          }
          notifyListeners();
        } catch (e) {
          // design/168d D1.15 — keep polling, but report once per cycle.
          if (!pollErrorReported) {
            pollErrorReported = true;
            unawaited(
              asrErrorReporter?.report(
                    kind: 'translate_poll_error',
                    message: e.toString(),
                    stage: 'translate_poll',
                    cacheId: cid,
                  ) ??
                  Future<void>.value(),
            );
          }
        }
      });
    }));
  }

  @override
  void dispose() {
    _stopTranslatePoll();
    super.dispose();
  }

  PaperEntry? paperEntryForCacheId(String cacheId) {
    final cid = cacheId.trim();
    for (final p in papers) {
      if (p.id == cid) return p;
    }
    return null;
  }

  Future<ReadingSession?> open(PaperEntry entry) async {
    // design/121 — open goes through GCS-first /open; errors stay in ``error``.
    if (!entry.isValid) {
      error = '잘못된 보관 항목입니다.';
      notifyListeners();
      return null;
    }
    opening = true;
    error = null;
    notifyListeners();
    final opId = 'open:${entry.id}';
    // design/130 — hang if open never returns (infinite spinner class).
    asrErrorReporter?.hang.begin(
      opId,
      stage: 'library_open',
      stallAfter: HangWatchdog.shortStall,
      paperTitle: entry.title,
      cacheId: entry.id,
    );
    try {
      final wantTr = await _wantTranslate();
      final o = await _client.openPaper(entry.id, translate: wantTr);
      asrErrorReporter?.hang.progress(opId, stage: 'library_open_ok');
      // Fail-closed: never keep a previous session when this open failed upstream.
      if (o.sentenceCount < 1) {
        error = '보관본에 문장이 없습니다. 재분석하거나 PDF를 다시 올려 주세요.';
        unawaited(
          asrErrorReporter?.report(
                kind: 'open_empty',
                message: 'open returned zero sentences',
                stage: 'library_open',
                paperTitle: entry.title,
                cacheId: entry.id,
              ) ??
              Future.value(),
        );
        return null;
      }
      if (o.title.isEmpty) o.title = entry.title;

      // design/123 — precise restore; invalid stored row → refuse open (no clamp).
      final uid = await _authUid();
      final raw = await loadProgressRaw(uid: uid, cacheId: o.cacheId);
      if (raw != null) {
        final v = validateProgressIndices(
          sentenceIndex: raw.sentenceIndex,
          figureIndex: raw.figureIndex,
          sentenceCount: o.sentenceCount,
          figureCount: o.figureCount,
        );
        if (!v.ok) {
          if (await _progressFailClosed()) {
            // WHY: product 4B — do not show a success reader with wrong cursor.
            error =
                '저장된 읽기 위치가 이 논문과 맞지 않습니다. 진행을 초기화한 뒤 다시 열어 주세요.';
            session = null;
            return null;
          }
          // KILL: ASR_PROGRESS_FAIL_CLOSED=0 — legacy clamp of stored values only.
          final si = raw.sentenceIndex;
          final fi = raw.figureIndex;
          o.sentenceIndex = si is int
              ? si
              : (si is num
                  ? si.toInt()
                  : int.tryParse('$si') ?? 0);
          o.figureIndex = fi is int
              ? fi
              : (fi is num
                  ? fi.toInt()
                  : int.tryParse('$fi') ?? 0);
          o.clampIndices();
        } else {
          o.sentenceIndex = v.sentenceIndex!;
          o.figureIndex = v.figureIndex!;
        }
      }

      session = o;
      _maybeShowQualityBanner(o);
      _maybeStartTranslatePoll(o);
      unawaited(_syncBookmarksForSession(o));
      unawaited(_syncAnnotationsForSession(o));
      // design/129 — fill current±1 images after sentences are on screen.
      unawaited(_prefetchFigureWindow());
      // design/80 — per-user chunk backfill (opt-in); errors surface on reader.
      unawaited(ensureShadowingChunks(entry.id));
      return session;
    } on AsrApiException catch (e) {
      // WHY: leave prior session untouched only if we never assigned; clear on fail.
      error = e.message;
      unawaited(
        asrErrorReporter?.reportApiFailure(
              e,
              stage: 'library_open',
              paperTitle: entry.title,
              cacheId: entry.id,
            ) ??
            Future.value(),
      );
      return null;
    } catch (e) {
      error = e.toString();
      unawaited(
        asrErrorReporter?.report(
              kind: 'open_exception',
              message: e.toString(),
              stage: 'library_open',
              paperTitle: entry.title,
              cacheId: entry.id,
            ) ??
            Future.value(),
      );
      return null;
    } finally {
      asrErrorReporter?.hang.end(opId);
      opening = false;
      notifyListeners();
    }
  }

  /// design/74 — open by cache id after notification tap (product 4B).
  Future<ReadingSession?> openByCacheId(String cacheId) async {
    final id = cacheId.trim();
    if (id.isEmpty) return null;
    PaperEntry? entry;
    for (final p in papers) {
      if (p.id == id) {
        entry = p;
        break;
      }
    }
    if (entry == null) {
      await refresh();
      for (final p in papers) {
        if (p.id == id) {
          entry = p;
          break;
        }
      }
    }
    if (entry == null) {
      error = '알림의 논문을 찾지 못했습니다. 보관함에서 열어 주세요.';
      notifyListeners();
      return null;
    }
    return open(entry);
  }

  Future<void> advanceSentence(int delta) async {
    final s = session;
    if (s == null || !s.isValid) return;
    final beforeFig = s.figureIndex;
    s.advanceSentence(delta);
    assert(s.figureIndex == beforeFig, 'figure index must stay put');
    notifyListeners();
    await _syncCursor(sentence: true);
    // design/123 — durable prefs on every sentence move (product 5C).
    await persistOpenedProgress();
  }

  Future<void> advanceFigure(int delta) async {
    final s = session;
    if (s == null || !s.isValid) return;
    final beforeSent = s.sentenceIndex;
    s.advanceFigure(delta);
    assert(s.sentenceIndex == beforeSent, 'sentence index must stay put');
    notifyListeners();
    unawaited(_prefetchFigureWindow());
    await _syncCursor(figure: true);
    // design/123 — durable prefs on every figure move (product 5C).
    await persistOpenedProgress();
  }

  /// Header picker jump — sentence index only (figure unchanged).
  Future<void> goToSentenceIndex(int index) async {
    final s = session;
    if (s == null || !s.isValid) return;
    if (s.sentenceCount < 1) return;
    if (index < 0 || index >= s.sentenceCount) return;
    if (index == s.sentenceIndex) return;
    final beforeFig = s.figureIndex;
    s.sentenceIndex = index;
    assert(s.figureIndex == beforeFig, 'sentence jump must not move figure');
    notifyListeners();
    await _syncCursor(sentence: true);
    await persistOpenedProgress();
  }

  /// design/28 · 124 — Fig. chip jump: figure index only (sentence unchanged).
  ///
  /// WHY fail-closed on OOB: do not clamp to a wrong figure (looks like success).
  Future<void> goToFigureIndex(int index) async {
    final s = session;
    if (s == null || !s.isValid) return;
    if (s.figureCount < 1) return;
    if (index < 0 || index >= s.figureCount) return;
    if (index == s.figureIndex) return;
    final beforeSent = s.sentenceIndex;
    s.figureIndex = index;
    assert(s.sentenceIndex == beforeSent, 'figure jump must not move sentence');
    notifyListeners();
    unawaited(_prefetchFigureWindow());
    await _syncCursor(figure: true);
    await persistOpenedProgress();
  }

  /// design/129 — fetch current±1 PNGs; never invent success on failure.
  Future<void> _prefetchFigureWindow() async {
    final s = session;
    if (s == null || !s.isValid || s.figureCount < 1) return;
    try {
      final rows = await _client.fetchFigureWindow(
        sessionId: s.sessionId,
        center: s.figureIndex,
        span: 1,
        cacheId: s.cacheId,
      );
      // EDGE: session may have changed while in flight.
      if (!identical(session, s)) return;
      s.mergeFigureWindow(rows);
      notifyListeners();
    } catch (e) {
      // design/168d G1.7 — fail-closed UI, but report (was silent).
      unawaited(
        asrErrorReporter?.report(
              kind: 'figure_window_error',
              message: e.toString(),
              stage: 'figure_window',
              cacheId: s.cacheId,
            ) ??
            Future<void>.value(),
      );
    }
  }

  Future<void> _syncCursor({bool sentence = false, bool figure = false}) async {
    final s = session;
    if (s == null || !s.isValid) return;
    try {
      await _client.patchCursor(
        sessionId: s.sessionId,
        sentenceIndex: sentence ? s.sentenceIndex : null,
        figureIndex: figure ? s.figureIndex : null,
      );
    } catch (_) {}
  }

  /// design/109 — user dismisses sticky ingest/library error banner.
  void dismissError() {
    if (error == null) return;
    error = null;
    notifyListeners();
  }

  /// design/158 — tap 「이어서 분석하기」 (same engine as auto-resume).
  Future<IngestJobResult?> resumeAnalysis() async {
    if (uploading || reanalyzing) return null;
    error = null;
    resumeOfferVisible = false;
    notifyListeners();
    return resumePendingIfAny();
  }

  /// design/158 — discard local upload draft (user opts out of resume).
  Future<void> discardResumeDraft() async {
    await _drafts.clear();
    await _cancelWorkmanager();
    resumeOfferVisible = false;
    error = null;
    notifyListeners();
  }

  void clearOpened() {
    shadowingChunksError = null;
    shadowingChunksCacheId = null;
    shadowingChunksBusy = false;
    session = null;
    notifyListeners();
  }

  Future<void> clearAll() async {
    // design/133 — latch cancel so a late upload Future cannot repopulate
    // papers after logout wipe. Leave the latch true until the next intentional
    // uploadPdf() clears it; do not re-arm mid-flight work here.
    // Server ingest cancel is out of scope this chip (local discard only).
    _uploadCancelRequested = true;
    _endIngestHang();
    shadowingChunksError = null;
    shadowingChunksCacheId = null;
    shadowingChunksBusy = false;
    papers = const [];
    session = null;
    error = null;
    resumeOfferVisible = false;
    loading = false;
    opening = false;
    uploading = false;
    uploadPercent = 0;
    uploadStage = '';
    uploadBackgroundHint = null;
    uploadBatteryHint = null;
    _activeContentHash = null;
    _activeUploadId = null;
    _activeJobId = null;
    await _cancelWorkmanager();
    await _editStash.purgeAll();
    await _drafts.clear();
    await _notify.stop();
    _stopStallWatch();
    notifyListeners();
  }

  static String sha256Hex(Uint8List bytes) => sha256.convert(bytes).toString();

  Future<void> _importDraftToEditStash(String cacheId) async {
    final draft = await _drafts.read();
    if (draft == null || draft.localPath.isEmpty) return;
    final cid = cacheId.trim();
    if (cid.isEmpty) return;
    await _editStash.importFromLocalPath(
      cacheId: cid,
      localPath: draft.localPath,
      contentHash: draft.contentHash,
    );
  }

  /// design/71·72 — auto resume processing job or chunked upload (with integrity).
  Future<IngestJobResult?> resumePendingIfAny() async {
    if (uploading) return null;
    final draft = await _drafts.read();
    if (draft == null) return null;

    if (draft.canReattach) {
      return _finishWithPoll(draft);
    }
    if (!draft.canResumeChunks || draft.localPath.isEmpty) {
      return null;
    }
    final raw = await _drafts.readLocalPdf(draft.localPath);
    if (raw == null || raw.isEmpty) {
      await _drafts.clear();
      return null;
    }
    final bytes = Uint8List.fromList(raw);
    final hash = sha256Hex(bytes);
    if (hash != draft.contentHash) {
      await _drafts.clear();
      error = '이어올리기 초안이 손상되어 삭제했습니다. 다시 골라 주세요.';
      notifyListeners();
      return null;
    }
    return uploadPdf(
      filename: draft.filename,
      bytes: bytes,
      knownHash: hash,
    );
  }



  /// design/80 · design/113 — backfill/retry; pending slices auto-continue.
  Future<void> ensureShadowingChunks(String cacheId) async {
    final id = cacheId.trim();
    if (id.isEmpty) return;
    shadowingChunksCacheId = id;
    final want = await _wantShadowingPractice();
    if (!want) {
      // WHY: preference/kill off → no banner success pretend.
      shadowingChunksError = null;
      shadowingChunksBusy = false;
      notifyListeners();
      return;
    }
    shadowingChunksBusy = true;
    shadowingChunksError = null;
    notifyListeners();
    try {
      final got = await _client.fetchShadowingChunks(id);
      final plan = got['plan'];
      final status = plan is Map ? plan['status']?.toString() : null;
      if (status == 'ok') {
        shadowingChunksError = null;
        return;
      }
      // design/113 — several budget slices until ok/error (cap avoids infinite).
      const maxSlices = 40;
      for (var i = 0; i < maxSlices; i++) {
        Map<String, dynamic> built;
        try {
          built = await _client.buildShadowingChunks(
            id,
            practiceEnabled: true,
          );
        } on AsrApiException catch (e) {
          // EDGE: legacy gateway 504 before budget fix — retry a few times.
          if (e.statusCode == 504 && i < 5) {
            await Future<void>.delayed(Duration(seconds: 2 + i));
            continue;
          }
          rethrow;
        }
        final p2 = built['plan'];
        final st2 = p2 is Map ? p2['status']?.toString() : null;
        if (st2 == 'ok') {
          shadowingChunksError = null;
          return;
        }
        if (st2 == 'pending' || built['continue'] == true) {
          // Honest in-progress — keep busy banner, next slice immediately.
          notifyListeners();
          continue;
        }
        if (st2 == 'error' || built['ok'] == false) {
          final msg = built['message']?.toString();
          shadowingChunksError =
              (msg != null && msg.isNotEmpty)
                  ? msg
                  : '연습 구간을 만들지 못했습니다. 다시 시도해 주세요.';
          return;
        }
        // Unknown shape — fail closed (no silent success).
        shadowingChunksError = '연습 구간을 만들지 못했습니다. 다시 시도해 주세요.';
        return;
      }
      shadowingChunksError =
          '연습 구간 준비가 길어집니다. 다시 시도해 주세요.';
    } on AsrApiException catch (e) {
      shadowingChunksError = e.message;
    } catch (_) {
      shadowingChunksError = '연습 구간 준비 중 오류가 났습니다. 다시 시도해 주세요.';
    } finally {
      shadowingChunksBusy = false;
      notifyListeners();
    }
  }

  Future<void> retryShadowingChunks() async {
    final cache = shadowingChunksCacheId;
    if (cache == null || cache.isEmpty) return;
    await ensureShadowingChunks(cache);
  }

  Future<bool> _wantShadowingPractice() async {
    try {
      final st = await _client.fetchStatus();
      if (!st.mobileShadowingPractice && !st.mobileShadowingChunks) {
        return false;
      }
      final auth = await _client.fetchAuthStatus();
      final uid = auth.user?.uid;
      if (uid == null || uid.isEmpty) return false;
      final p = await SharedPreferences.getInstance();
      return parseShadowingEnabledPref(p.getString(shadowingPrefsKey(uid)));
    } catch (_) {
      return false;
    }
  }

  /// design/99 — Settings translate opt-in (default OFF).
  Future<bool> _wantTranslate() async {
    try {
      final auth = await _client.fetchAuthStatus();
      final uid = auth.user?.uid;
      if (uid == null || uid.isEmpty) return false;
      final p = await SharedPreferences.getInstance();
      return parseTranslateEnabledPref(p.getString(translatePrefsKey(uid)));
    } catch (_) {
      return false;
    }
  }

  /// design/132 — cancel early upload/ingest; late stages may refuse (too late).
  Future<void> cancelUpload() async {
    if (!uploading || _uploadCancelRequested) return;
    // WHY: pre-CD live has no cancel route — a bare 404 must not look like success wipe.
    try {
      final st = await _client.fetchStatus();
      if (!st.mobileIngestCancel) {
        error = '지금은 취소를 사용할 수 없습니다.';
        notifyListeners();
        return;
      }
    } catch (_) {
      // EDGE: status probe failed — refuse cancel rather than fake discard.
      error = '지금은 취소를 사용할 수 없습니다.';
      notifyListeners();
      return;
    }
    _uploadCancelRequested = true;
    notifyListeners();
    final upl = (_activeUploadId ?? '').trim();
    final job = (_activeJobId ?? '').trim();
    try {
      if (upl.isNotEmpty) {
        try {
          await _client.cancelChunkedUpload(upl);
        } on AsrApiException catch (e) {
          // 404 already gone — continue; 503 surface below.
          if (e.statusCode == 503) {
            error = e.message;
            _uploadCancelRequested = false;
            notifyListeners();
            return;
          }
        }
      }
      if (job.isNotEmpty) {
        final r = await _client.cancelIngestJob(job);
        if (r.tooLate) {
          // Product: let it finish — clear cancel flag so poll continues.
          _uploadCancelRequested = false;
          error = '거의 끝나 취소할 수 없습니다. 그대로 완료됩니다.';
          notifyListeners();
          return;
        }
      }
    } on AsrApiException catch (e) {
      if (e.statusCode == 503) {
        error = e.message;
        _uploadCancelRequested = false;
        notifyListeners();
        return;
      }
      // Other errors: still stop local work; server may already be wiped.
    }
    await _drafts.clear();
    await _cancelWorkmanager();
    await _notify.showFailed(message: '업로드를 취소했습니다.');
  }

  Future<IngestJobResult?> uploadPdf({
    required String filename,
    required Uint8List bytes,
    String? knownHash,
  }) async {
    if (uploading) {
      error = '이미 업로드 중입니다.';
      notifyListeners();
      return null;
    }

    final hash = knownHash ?? sha256Hex(bytes);
    final existing = await _drafts.read();
    if (existing != null &&
        existing.contentHash == hash &&
        existing.canReattach) {
      return _finishWithPoll(existing);
    }

    String? resumeUploadId;
    if (existing != null &&
        existing.contentHash == hash &&
        existing.canResumeChunks) {
      try {
        final st = await _client.getChunkedUpload(existing.uploadId);
        if (st.contentHash == hash &&
            st.size == bytes.length &&
            (st.receivedOffset == 0 ||
                AsrClient.sha256Hex(bytes.sublist(0, st.receivedOffset)) ==
                    st.prefixSha256)) {
          resumeUploadId = existing.uploadId;
        } else {
          await _drafts.clear();
        }
      } on AsrApiException {
        await _drafts.clear();
      }
    }

    uploading = true;
    uploadPercent = 0;
    uploadStage = '준비 중';
    error = null;
    uploadBackgroundHint = null;
    _wmEnabledCache = null;
    _activeContentHash = hash;
    _uploadCancelRequested = false;
    _activeUploadId = resumeUploadId;
    _activeJobId = null;
    await _maybeOfferBatteryHint(hash);
    _startStallWatch();
    await _beginIngestHang(filename: filename);
    notifyListeners();

    // design/74 — product 1A: notify when enabled; upload continues either way.
    final startedNotify = await _maybeStartNotify('준비 중');
    if (startedNotify.permissionDeniedHint) {
      uploadBackgroundHint =
          '알림·백그라운드 권한이 없어 업로드가 중간에 끊길 수 있습니다.';
      notifyListeners();
    }
    // design/76 — arm delayed WM as soon as a draft can exist.
    await _scheduleWorkmanager(immediate: false);

    try {
      final localPath = await _drafts.saveLocalPdf(hash, bytes);
      var draft = UploadDraft(
        contentHash: hash,
        filename: filename.trim(),
        phase: 'uploading',
        localPath: localPath ?? '',
        bytesLen: bytes.length,
        uploadId: resumeUploadId ?? '',
      );
      await _drafts.write(draft);

      late final String jobId;
      try {
        final wantShadow = await _wantShadowingPractice();
        final wantTr = await _wantTranslate();
        final started = await _client.startIngestPdfBytesChunked(
          filename: filename,
          bytes: bytes,
          contentHash: hash,
          existingUploadId: resumeUploadId,
          shadowingPractice: wantShadow,
          translate: wantTr,
          isCancelled: () => _uploadCancelRequested,
          onProgress: (pct, msg) {
            _touchProgress();
            uploadPercent = pct;
            uploadStage = msg.isEmpty ? '조각 올리는 중' : msg;
            _noteIngestHangProgress(percent: uploadPercent, stage: uploadStage);
            notifyListeners();
            unawaited(
              _notify.updateProgress(
                percent: uploadPercent,
                stage: uploadStage,
              ),
            );
          },
          onUploadId: (upl) async {
            _activeUploadId = upl;
            draft = draft.copyWith(uploadId: upl, phase: 'uploading');
            await _drafts.write(draft);
            // Upload id assigned is real forward progress.
            _noteIngestHangProgress(percent: uploadPercent, stage: 'uploading');
          },
        );
        jobId = started.jobId;
        _activeJobId = started.jobId;
        draft = draft.copyWith(
          uploadId: started.uploadId,
          jobId: started.jobId,
          phase: 'processing',
        );
      } on AsrApiException catch (e) {
        if (e.statusCode != 503) rethrow;
        final started = await _client.startIngestPdfBytes(
          filename: filename,
          bytes: bytes,
          shadowingPractice: await _wantShadowingPractice(),
          translate: await _wantTranslate(),
        );
        jobId = started.jobId;
        _activeJobId = started.jobId;
        draft = draft.copyWith(
          uploadId: '',
          jobId: started.jobId,
          phase: 'processing',
        );
        uploadStage = '업로드 완료, 처리 중';
      }
      await _drafts.write(draft);
      _touchProgress();
      uploadPercent = 50;
      uploadStage = '처리 중';
      _noteIngestHangProgress(percent: 50, stage: 'processing');
      notifyListeners();
      await _notify.updateProgress(percent: 50, stage: '처리 중');

      final result = await _client.pollIngestJob(
        jobId: jobId,
        isCancelled: () => _uploadCancelRequested,
        onProgress: (pct, msg) {
          _touchProgress();
          uploadPercent = 50 + (pct.clamp(0, 100) ~/ 2);
          uploadStage = msg.isEmpty ? '처리 중' : msg;
          _noteIngestHangProgress(percent: uploadPercent, stage: uploadStage);
          notifyListeners();
          unawaited(
            _notify.updateProgress(
              percent: uploadPercent,
              stage: uploadStage,
            ),
          );
        },
      );
      await _importDraftToEditStash(result.cacheId);
      await _drafts.clear();
      await _cancelWorkmanager();
      await refresh();
      final seen = papers.any((p) => p.id == result.cacheId);
      if (!seen) {
        error = '업로드는 끝났지만 목록에 아직 없습니다. 새로고침해 주세요.';
        await _notify.showFailed(message: error!);
        notifyListeners();
        return null;
      }
      await _notify.showCompleted(cacheId: result.cacheId);
      return result;
    } on UploadCancelledException {
      // design/132 — honest cancel; design/134 hang keeps failure message.
      await _drafts.clear();
      await _cancelWorkmanager();
      if (!_ingestHangTripped) {
        error = null;
      }
      await refresh();
      return null;
    } on AsrApiException catch (e) {
      // design/109: terminal job (422) or lost/conflict — do not reattach forever.
      if (e.statusCode == 409 ||
          e.statusCode == 404 ||
          e.statusCode == 422) {
        await _drafts.clear();
        await _cancelWorkmanager();
        resumeOfferVisible = false;
      } else if (e.statusCode == 504 || _ingestHangTripped) {
        resumeOfferVisible = await _draftResumable();
      }
      // design/105 — surface last stage on timeout so failure is actionable.
      final stage = uploadStage.trim();
      if (e.statusCode == 504 && stage.isNotEmpty) {
        error = '${e.message} ($stage)';
      } else {
        error = e.message;
      }
      await _notify.showFailed(message: error!);
      return null;
    } catch (e) {
      error = e.toString();
      await _notify.showFailed(message: error!);
      return null;
    } finally {
      _endIngestHang();
      uploading = false;
      uploadPercent = 0;
      uploadStage = '';
      uploadBatteryHint = null;
      _activeContentHash = null;
      _activeUploadId = null;
      _activeJobId = null;
      _uploadCancelRequested = false;
      _ingestHangTripped = false;
      _stopStallWatch();
      notifyListeners();
      unawaited(_refreshResumeOffer());
    }
  }

  Future<IngestJobResult?> _finishWithPoll(UploadDraft draft) async {
    uploading = true;
    uploadPercent = 0;
    uploadStage = '이어올리는 중';
    error = null;
    uploadBackgroundHint = null;
    _wmEnabledCache = null;
    _activeContentHash = draft.contentHash;
    _uploadCancelRequested = false;
    _activeUploadId = draft.uploadId.isEmpty ? null : draft.uploadId;
    _activeJobId = draft.jobId.isEmpty ? null : draft.jobId;
    await _maybeOfferBatteryHint(draft.contentHash);
    _startStallWatch();
    await _beginIngestHang(filename: draft.filename);
    notifyListeners();
    final startedNotify = await _maybeStartNotify('이어올리는 중');
    if (startedNotify.permissionDeniedHint) {
      uploadBackgroundHint =
          '알림·백그라운드 권한이 없어 업로드가 중간에 끊길 수 있습니다.';
      notifyListeners();
    }
    await _scheduleWorkmanager(immediate: false);
    try {
      final result = await _client.pollIngestJob(
        jobId: draft.jobId,
        isCancelled: () => _uploadCancelRequested,
        onProgress: (pct, msg) {
          _touchProgress();
          uploadPercent = pct;
          uploadStage = msg.isEmpty ? '이어올리는 중' : msg;
          _noteIngestHangProgress(percent: uploadPercent, stage: uploadStage);
          notifyListeners();
          unawaited(
            _notify.updateProgress(
              percent: uploadPercent,
              stage: uploadStage,
            ),
          );
        },
      );
      await _importDraftToEditStash(result.cacheId);
      await _drafts.clear();
      await _cancelWorkmanager();
      await refresh();
      final seen = papers.any((p) => p.id == result.cacheId);
      if (!seen) {
        error = '업로드는 끝났지만 목록에 아직 없습니다. 새로고침해 주세요.';
        await _notify.showFailed(message: error!);
        notifyListeners();
        return null;
      }
      await _notify.showCompleted(cacheId: result.cacheId);
      return result;
    } on UploadCancelledException {
      await _drafts.clear();
      await _cancelWorkmanager();
      if (!_ingestHangTripped) {
        error = null;
      }
      await refresh();
      return null;
    } on AsrApiException catch (e) {
      // design/109: same terminal cleanup as uploadPdf.
      if (e.statusCode == 409 ||
          e.statusCode == 404 ||
          e.statusCode == 422) {
        await _drafts.clear();
        await _cancelWorkmanager();
        resumeOfferVisible = false;
      } else if (e.statusCode == 504 || _ingestHangTripped) {
        resumeOfferVisible = await _draftResumable();
      }
      final stage = uploadStage.trim();
      if (e.statusCode == 504 && stage.isNotEmpty) {
        error = '${e.message} ($stage)';
      } else {
        error = e.message;
      }
      await _notify.showFailed(message: error!);
      return null;
    } catch (e) {
      error = e.toString();
      await _notify.showFailed(message: error!);
      return null;
    } finally {
      _endIngestHang();
      uploading = false;
      uploadPercent = 0;
      uploadStage = '';
      uploadBatteryHint = null;
      _activeContentHash = null;
      _activeUploadId = null;
      _activeJobId = null;
      _uploadCancelRequested = false;
      _ingestHangTripped = false;
      _stopStallWatch();
      notifyListeners();
      unawaited(_refreshResumeOffer());
    }
  }
}
