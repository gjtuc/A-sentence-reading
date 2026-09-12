/// Paper library + opened reading session (design/62 · 70 · 71 · 72 · 74 · 75 · 76).
library;

import 'dart:async';
import 'dart:io';
import 'dart:convert';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/client.dart';
import '../api/fig_refs.dart' as fig;
import '../api/ingest_models.dart';
import '../api/paper_models.dart';
import '../api/progress_gate.dart';
import '../api/progress_store.dart';
import '../api/reading_models.dart';
import '../api/upload_draft_models.dart';
import '../api/upload_draft_store.dart';
import '../api/upload_reserve_models.dart';
import '../api/upload_reserve_store.dart';
import '../api/upload_picker_recent_models.dart';
import '../api/upload_picker_recent_store.dart';
import '../api/pdf_folder_grant_models.dart';
import '../pdf/normalize_pairing_key.dart';
import '../api/pdf_folder_grant_store.dart';
import '../api/pdf_hash_cache_store.dart';
import '../api/pdf_advisory_cache_store.dart';
import '../api/document_citation.dart';
import '../pdf/doc_role_detect.dart';
import '../pdf/advisory_title.dart';
import '../api/library_soft_delete_store.dart';
import '../platform/saf_tree_channel.dart';
import '../api/upload_notify.dart';
import '../api/shadowing_models.dart';
import '../api/translate_models.dart';
import '../api/library_order_models.dart';
import '../api/bookmark_models.dart';
import '../state/bookmark_controller.dart';
import '../state/annotation_controller.dart';
import '../services/error_reporter.dart';
import '../services/evidence_bus.dart';
import '../services/figure_disk_cache.dart';
import '../services/paper_disk_store.dart';
import '../services/shadowing_cloud_migrate.dart';
import '../services/hang_watchdog.dart';
import '../services/paper_edit_stash.dart';
import '../services/shadowing_disk_store.dart';
import 'ingest_auto_resume.dart';
import 'figure_hydrate.dart';
import 'harmonize_residual.dart';

/// Stall after this long without progress while an upload is marked active.
const Duration kUploadStallAfter = Duration(seconds: 45);

/// Loads `/api/cache/papers`, opens a cache entry, advances cursors independently.
class LibraryController extends ChangeNotifier {
  LibraryController({
    required AsrClient client,
    UploadDraftStore? draftStore,
    UploadReserveStore? reserveStore,
    UploadPickerRecentStore? pickerRecentStore,
    PdfFolderGrantStore? pdfFolderGrantStore,
    PdfFolderGrantStore? pdfDownloadsGrantStore,
    PdfHashCacheStore? pdfHashCacheStore,
    PdfAdvisoryCacheStore? pdfAdvisoryCacheStore,
    SafTreeChannel? safTreeChannel,
    LibrarySoftDeleteStore? softDeleteStore,
    UploadNotify? uploadNotify,
    PaperEditStash? editStash,
    FigureDiskCache? figureDiskCache,
    PaperDiskStore? paperDiskStore,
    /// Settings toggle — preferred over prefs re-read (avoids auth blip → translate=0).
    bool Function()? translateEnabled,
  })  : _client = client,
        _drafts = draftStore ?? PrefsUploadDraftStore(),
        _reserve = reserveStore ?? PrefsUploadReserveStore(),
        _pickerRecent = pickerRecentStore ?? PrefsUploadPickerRecentStore(),
        _pdfFolderGrant = pdfFolderGrantStore ?? PrefsPdfFolderGrantStore(),
        _pdfDownloadsGrant =
            pdfDownloadsGrantStore ?? prefsPdfDownloadsGrantStore(),
        _pdfHashCache = pdfHashCacheStore ?? PdfHashCacheStore(),
        _pdfAdvisoryCache = pdfAdvisoryCacheStore ?? PdfAdvisoryCacheStore(),
        _safTree = safTreeChannel ?? SafTreeChannel(),
        _softDelete = softDeleteStore ?? PrefsLibrarySoftDeleteStore(),
        _notify = uploadNotify ?? createUploadNotify(),
        _editStash = editStash ?? PaperEditStash(),
        _figureDisk = figureDiskCache ?? FigureDiskCache(),
        _paperDisk = paperDiskStore ?? PaperDiskStore(),
        _translateEnabled = translateEnabled;

  final AsrClient _client;
  final UploadDraftStore _drafts;
  final UploadReserveStore _reserve;
  final UploadPickerRecentStore _pickerRecent;
  final PdfFolderGrantStore _pdfFolderGrant;
  final PdfFolderGrantStore _pdfDownloadsGrant;
  final PdfHashCacheStore _pdfHashCache;
  final PdfAdvisoryCacheStore _pdfAdvisoryCache;
  final SafTreeChannel _safTree;
  final LibrarySoftDeleteStore _softDelete;
  final UploadNotify _notify;
  final PaperEditStash _editStash;
  final FigureDiskCache _figureDisk;
  final PaperDiskStore _paperDisk;
  bool _shadowingLocalSot = false;
  bool Function()? _translateEnabled;

  /// Wire after [TranslateController] exists (app root).
  void attachTranslateEnabled(bool Function() enabled) {
    _translateEnabled = enabled;
  }

  PaperEditStash get editStash => _editStash;
  FigureDiskCache get figureDiskCache => _figureDisk;
  PaperDiskStore get paperDiskStore => _paperDisk;

  /// design/171 · 185 — bind disk caches to signed-in uid (no cross-user reads).
  
  /// design/187 — when true, one-shot migrate shadowing/voice then wipe GCS.
  void setShadowingLocalSot(bool next) {
    _shadowingLocalSot = next;
  }

  void bindFigureDiskUid(String? uid) {
    _diskUid = (uid ?? '').trim().isEmpty ? null : uid!.trim();
    _figureDisk.bindUid(uid);
    _paperDisk.bindUid(uid);
    _shadowDisk.bindUid(uid);
    unawaited(_pickerRecent.bindUid(_diskUid));
    unawaited(_pdfFolderGrant.bindUid(_diskUid));
    unawaited(_pdfDownloadsGrant.bindUid(_diskUid));
    unawaited(_pdfHashCache.bindUid(_diskUid));
    unawaited(_pdfAdvisoryCache.bindUid(_diskUid));
    unawaited(_pickerRecentThenSoftDelete());
    _bulkHandoffAttempted = false;
    _clearPendingEnrichState();
  }

  Future<void> _pickerRecentThenSoftDelete() async {
    await _reloadPickerRecent();
    await _softDelete.bindUid(_diskUid);
    // design/224 — drop due soft-hides, then refilter list.
    await purgeDueSoftDeletes();
    _publishPapers(papers);
    notifyListeners();
    _scheduleSoftPurgeWorker();
  }

  String? _diskUid;
  final ShadowingDiskStore _shadowDisk = ShadowingDiskStore();
  BookmarkController? _bookmarks;
  AnnotationController? _annotations;
  Timer? _softPurgeTimer;

  /// design/224 — filter soft-hidden ids before publishing list.
  void _publishPapers(List<PaperEntry> next) {
    final hidden = _softDelete.hiddenIds;
    final filtered = hidden.isEmpty
        ? next
        : next.where((e) => !hidden.contains(e.id)).toList(growable: false);
    // design/240 — adjacent mates; still two openable rows (no auto-merge).
    papers = pairAdjacentPapers(filtered);
  }

  void _scheduleSoftPurgeWorker() {
    _softPurgeTimer?.cancel();
    final earliest = _softDelete.snapshot.earliestPurgeAtMs;
    if (earliest == null) return;
    final now = DateTime.now().millisecondsSinceEpoch;
    final delayMs = earliest <= now ? 0 : earliest - now;
    _softPurgeTimer = Timer(Duration(milliseconds: delayMs), () {
      unawaited(() async {
        await purgeDueSoftDeletes();
        _scheduleSoftPurgeWorker();
      }());
    });
  }

  /// design/224 — hide locally; hard DELETE after purge_at (wall clock).
  Future<int> softHidePapers(Iterable<String> cacheIds) async {
    final ids = cacheIds
        .map((e) => e.trim())
        .where((e) => e.isNotEmpty)
        .toSet()
        .toList(growable: false);
    if (ids.isEmpty) return 0;
    final list = await _softDelete.hide(ids);
    final purgeAt = list.entries
        .where((e) => ids.contains(e.cacheId))
        .map((e) => e.purgeAtMs)
        .fold<int?>(null, (a, b) => a == null ? b : (a < b ? a : b));
    asrEvidenceBus?.record(
      'paper_soft_hide',
      severity: 'lifecycle',
      stage: 'hide',
      ok: true,
      details: {
        'n': ids.length,
        if (purgeAt != null) 'purge_at_ms': purgeAt,
      },
    );
    final openId = session?.cacheId;
    if (openId != null && ids.contains(openId)) {
      clearOpened();
      // design/225 224b — leave reader surface (Offstage keep-alive).
      onSoftHideOpened?.call();
    }
    _publishPapers(papers.where((p) => !ids.contains(p.id)).toList());
    error = null;
    notifyListeners();
    _scheduleSoftPurgeWorker();
    return ids.length;
  }

  /// design/224 — restore soft-hidden rows via refresh (server/disk still hold them).
  Future<int> undoSoftHide(Iterable<String> cacheIds) async {
    final ids = cacheIds
        .map((e) => e.trim())
        .where((e) => e.isNotEmpty)
        .toSet()
        .toList(growable: false);
    if (ids.isEmpty) return 0;
    await _softDelete.undo(ids);
    asrEvidenceBus?.record(
      'paper_soft_undo',
      severity: 'lifecycle',
      stage: 'undo',
      ok: true,
      details: {'n': ids.length},
    );
    await refresh(fresh: false, clearError: false, trigger: 'soft_undo');
    _scheduleSoftPurgeWorker();
    return ids.length;
  }

  /// design/224 — hard-delete entries whose purge_at has passed.
  Future<int> purgeDueSoftDeletes({int? nowMs}) async {
    await _softDelete.read();
    final now = nowMs ?? DateTime.now().millisecondsSinceEpoch;
    final due = _softDelete.snapshot.dueAt(now);
    if (due.isEmpty) return 0;
    var purged = 0;
    for (final e in due) {
      // Per-id so soft-store removal tracks HTTP honesty (design/177 + 224).
      final n = await deletePapers([e.cacheId]);
      if (n > 0) {
        await _softDelete.remove([e.cacheId]);
        purged += 1;
      }
    }
    _scheduleSoftPurgeWorker();
    return purged;
  }

  void attachBookmarks(BookmarkController bookmarks) {
    _bookmarks = bookmarks;
    bookmarks.attachClient(_client);
  }

  void attachAnnotations(AnnotationController annotations) {
    _annotations = annotations;
    annotations.attachClient(_client);
  }

  /// design/183 — fired after a real sentence_index change (advance / jump).
  void Function(int from, int to)? onSentenceIndexChanged;

  /// design/225 — soft-hide cleared the open session; shell should leave reader.
  VoidCallback? onSoftHideOpened;

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
  /// Survives snackbar dismiss — last reanalyze/ingest failure for diagnosis.
  String? lastIngestFailure;
  /// design/80 — fail-closed banner when chunk plan missing/failed.
  String? shadowingChunksError;
  String? shadowingChunksCacheId;
  /// design/113 · 0.3.176 — soft progress while pending (e.g. 29/301).
  String? shadowingChunksProgress;
  bool shadowingChunksBusy = false;
  /// Single-flight: handoff+open must not race two builds (progress reset).
  Future<void>? _shadowingEnsureFuture;
  String? _shadowingEnsureCacheId;

  /// design/99 — KO backfill polling after /open (translate_pending).
  bool translateBackfillBusy = false;

  /// design/195 — library-wide resume of unfinished KO + shadowing.
  bool pendingEnrichBusy = false;
  String? pendingEnrichCacheId;
  String? pendingEnrichTrigger;
  final List<String> _enrichQueue = [];
  final Map<String, int> _enrichFailCount = {};
  final Set<String> _enrichInQueue = {};
  bool _enrichLoopBusy = false;
  Timer? _enrichRetryTimer;
  static const int kPendingEnrichMaxRetries = 3;
  Timer? _translatePollTimer;

  /// design/167 — show ingest quality banner once per open until dismissed.
  bool showIngestQualityBanner = false;
  String? _dismissedQualityBannerCacheId;

  /// design/160 — uid-scoped read-left timestamps for library meta lines.
  Map<String, String> progressResumeByCacheId = const {};
  String readerLayoutMode = 'split';
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

  /// design/221 — durable FIFO reservation queue (serial pump → uploadPdf).
  List<UploadReserveItem> uploadQueue = const [];
  bool _uploadPumpBusy = false;
  bool _uploadQueueAutoOpened = false;

  /// design/221 — first_only auto-open; library screen consumes then clears.
  String? pendingAutoOpenCacheId;

  /// design/223 — recent pick metadata (uid-scoped).
  List<PickerRecentItem> pickerRecent = const [];

  /// design/223 — library content hashes for green border (list ∪ disk).
  Set<String> libraryContentHashes = const {};

  /// design/226 — connected folder grant + scanned PDF rows.
  PdfFolderGrant? pdfFolderGrant;
  List<ScannedPdfEntry> pdfFolderEntries = const [];
  bool pdfFolderTruncated = false;
  bool pdfFolderGrantStale = false;
  bool _pdfHashPumpBusy = false;
  bool _pdfAdvisoryPumpBusy = false;
  int _pdfAdvisoryPumpEpoch = 0;
  int _pdfFolderRescanDebounceMs = 0;

  /// design/241 — proactive tree writable probe (null = unknown / no grant).
  bool? pdfFolderWritable;

  /// design/248 — Downloads tree browse (separate grant; PDF-only list).
  PdfImportBrowseMode pdfImportBrowseMode = PdfImportBrowseMode.papers;
  PdfFolderGrant? pdfDownloadsGrant;
  List<ScannedPdfEntry> pdfDownloadsEntries = const [];
  bool pdfDownloadsTruncated = false;
  bool pdfDownloadsGrantStale = false;
  int _pdfDownloadsRescanDebounceMs = 0;

  /// design/242 — tree-only find-watch after DOI CTA (no MES).
  bool pdfFindWatchArmed = false;
  int pdfFindWatchUntilMs = 0;
  int pdfFindWatchBaselineMs = 0;
  String? pdfFindWatchHitDocUri;
  bool _pdfFindWatchHandled = false;
  final Set<String> _pdfFindWatchIgnoreUris = {};

  void consumePendingAutoOpen() {
    pendingAutoOpenCacheId = null;
  }

  /// design/132 — user asked to cancel the in-flight upload/ingest.
  bool _uploadCancelRequested = false;
  String? _activeUploadId;
  String? _activeJobId;

  /// design/169g phase 4 — last open→reader handoff for nav_tab join.
  String? _lastOpenHandoffId;

  /// Consume open→reader handoff id (once) for nav_tab evidence.
  String? takeOpenHandoffId() {
    final id = _lastOpenHandoffId;
    _lastOpenHandoffId = null;
    return id;
  }

  /// design/134 — hang watchdog op for current upload attempt (stable per try).
  String? _hangOpId;
  bool _ingestHangTripped = false;
  bool _hangLocalBound = false;
  int _hangLastPercent = -1;
  String _hangLastStageKey = '';
  String _hangLastMessage = '';
  bool _hangTranslateStallArmed = false;

  DateTime? _lastProgressAt;
  Timer? _stallWatch;
  bool _resumeInFlight = false;
  /// Cached for one upload session — avoid /api/status on every chunk heartbeat.
  bool? _wmEnabledCache;
  DateTime? _lastWmScheduleAt;

  /// Per-stage consecutive timeout auto-resume (max [kIngestAutoResumeMax]).
  final IngestAutoResumeGate _autoResumeGate = IngestAutoResumeGate();
  /// Set in catch; consumed in finally after uploading latch clears.
  bool _pendingAutoResume = false;

  /// design/169n — library background figure byte hydrate (per cache_id).
  final Map<String, FigureHydrateSnapshot> _figureHydrate = {};
  final Map<String, ReadingSession> _hydrateSessions = {};
  final List<String> _hydrateQueue = [];
  final Set<String> _hydrateDismissed = {};
  bool _hydrateLoopBusy = false;
  int _hydrateGeneration = 0;
  /// design/180 — cacheIds currently in hydrate loop (prefetch skip).
  final Set<String> _hydrateActive = {};
  /// design/180 — single in-flight figure network gate (hydrate + prefetch).
  Future<void> _figureNetTail = Future<void>.value();

  ReadingSession? get opened => session;

  /// design/169n — library row label (empty when hidden).
  String figureHydrateLabel(String cacheId) {
    final s = _figureHydrate[cacheId.trim()];
    if (s == null) return '';
    return s.userLabel;
  }

  FigureHydrateSnapshot? figureHydrateSnapshot(String cacheId) =>
      _figureHydrate[cacheId.trim()];

  void dismissFigureHydrate(String cacheId) {
    final cid = cacheId.trim();
    if (cid.isEmpty) return;
    _hydrateDismissed.add(cid);
    _figureHydrate.remove(cid);
    notifyListeners();
  }

  /// Enqueue post-ingest / retry figure byte hydrate for [cacheId].
  void enqueueFigureHydrate(String cacheId, {bool force = false}) {
    final cid = cacheId.trim();
    if (cid.isEmpty) return;
    if (!force && _hydrateDismissed.contains(cid)) return;
    if (force) _hydrateDismissed.remove(cid);
    final cur = _figureHydrate[cid];
    if (!force &&
        cur != null &&
        (cur.phase == FigureHydratePhase.arming ||
            cur.phase == FigureHydratePhase.hydrating ||
            cur.phase == FigureHydratePhase.doneOk)) {
      return;
    }
    if (!_hydrateQueue.contains(cid)) {
      _hydrateQueue.add(cid);
    }
    unawaited(_pumpFigureHydrateQueue());
  }

  Future<void> _pumpFigureHydrateQueue() async {
    if (_hydrateLoopBusy) return;
    _hydrateLoopBusy = true;
    try {
      while (_hydrateQueue.isNotEmpty) {
        final cid = _hydrateQueue.removeAt(0);
        if (_hydrateDismissed.contains(cid)) continue;
        await _runFigureHydrate(cid);
      }
    } finally {
      _hydrateLoopBusy = false;
      if (_hydrateQueue.isNotEmpty) {
        unawaited(_pumpFigureHydrateQueue());
      }
    }
  }

  /// design/180 — serialize all figure PNG/window network fetches app-wide.
  Future<T> _withFigureNetGate<T>(Future<T> Function() op) async {
    final prev = _figureNetTail;
    final done = Completer<void>();
    _figureNetTail = done.future;
    await prev;
    try {
      return await op();
    } finally {
      if (!done.isCompleted) done.complete();
    }
  }

  List<int> _emptyFigureIndexes(ReadingSession hs) {
    final out = <int>[];
    for (var i = 0; i < hs.figures.length; i++) {
      if (hs.figures[i].imageSrc.trim().isEmpty) out.add(i);
    }
    return out;
  }

  /// design/171 — fill empty imageSrc from on-device PNG cache.
  Future<({int hit, int miss})> _injectFiguresFromDisk(ReadingSession hs) async {
    var hit = 0;
    var miss = 0;
    final ch = hs.contentHash;
    if (ch.isNotEmpty) {
      await _figureDisk.ensureContentHash(hs.cacheId, ch);
    }
    for (final f in hs.figures) {
      if (f.id.isEmpty) continue;
      if (f.imageSrc.trim().isNotEmpty) {
        hit++;
        continue;
      }
      final url = await _figureDisk.readDataUrl(hs.cacheId, f.id);
      if (url != null && url.isNotEmpty) {
        f.imageSrc = url;
        hit++;
      } else {
        miss++;
      }
    }
    return (hit: hit, miss: miss);
  }

  Future<void> _persistFiguresFromWindowRows(
    String cacheId,
    List<Map<String, dynamic>> rows, {
    String contentHash = '',
  }) async {
    for (final row in rows) {
      final id = '${row['id'] ?? ''}'.trim();
      final src = '${row['image_src'] ?? ''}'.trim();
      if (id.isEmpty || src.isEmpty) continue;
      await _figureDisk.writeDataUrl(
        cacheId,
        figureId: id,
        imageSrc: src,
        contentHash: contentHash,
      );
    }
  }

  Future<void> _runFigureHydrate(String cacheId) async {
    final cid = cacheId.trim();
    if (cid.isEmpty) return;
    final gen = ++_hydrateGeneration;
    final attempt = (_figureHydrate[cid]?.attemptN ?? 0) + 1;
    _hydrateActive.add(cid);
    _figureHydrate[cid] = FigureHydrateSnapshot(
      cacheId: cid,
      phase: FigureHydratePhase.arming,
      total: 0,
      filled: 0,
      failed: 0,
      attemptN: attempt,
    );
    notifyListeners();

    try {
      ReadingSession? hs;
      // design/185 J23 — prefer local disk session before cloud /open.
      if (await _paperDisk.hasSession(cid)) {
        final raw = await _paperDisk.loadSessionJson(cid);
        if (raw != null) {
          try {
            final local = ReadingSession.fromOpenJson(
              raw,
              fallbackTitle: cid,
              fallbackCacheId: cid,
            );
            for (var i = 0; i < local.figures.length; i++) {
              final f = local.figures[i];
              if (f.imageSrc.trim().isNotEmpty) continue;
              final bytes = await _paperDisk.readFigureBytes(cid, f.id);
              if (bytes == null || bytes.isEmpty) continue;
              local.figures[i].imageSrc = figureDataUrlFromBytes(bytes);
            }
            hs = local;
          } catch (_) {
            hs = null;
          }
        }
      }
      try {
        if (hs == null) {
          final wantTr = await _wantTranslate();
          hs = await _client.openPaper(cid, translate: wantTr);
        }
      } catch (e) {
        if (hs == null) {
          _figureHydrate[cid] = FigureHydrateSnapshot(
            cacheId: cid,
            phase: FigureHydratePhase.aborted,
            total: 0,
            filled: 0,
            failed: 0,
            attemptN: attempt,
            abortReason: 'open_failed',
          );
          asrEvidenceBus?.record(
            'figure_hydrate_abort',
            severity: 'error',
            cacheId: cid,
            stage: 'arming',
            ok: false,
            details: {'abort_reason': 'open_failed', 'attempt_n': attempt},
            message: e.toString().length > 200
                ? e.toString().substring(0, 200)
                : e.toString(),
          );
          notifyListeners();
          return;
        }
      }
      if (hs == null) return;
      if (gen != _hydrateGeneration && _hydrateDismissed.contains(cid)) {
        return;
      }
      if (hs.figureCount < 1) {
        _figureHydrate[cid] = FigureHydrateSnapshot(
          cacheId: cid,
          phase: FigureHydratePhase.doneOk,
          total: 0,
          filled: 0,
          failed: 0,
          attemptN: attempt,
        );
        asrEvidenceBus?.record(
          'figure_hydrate_done',
          severity: 'boundary',
          cacheId: cid,
          stage: 'hydrate_bg',
          ok: true,
          details: {'total': 0, 'filled': 0, 'failed': 0, 'attempt_n': attempt},
        );
        notifyListeners();
        return;
      }

      // Merge any prior hydrate bytes; keep side session for open() preserve.
      final prior = _hydrateSessions[cid];
      if (prior != null) {
        hs.preserveClientStateFrom(prior);
      }
      if (session?.cacheId == cid) {
        hs.preserveClientStateFrom(session);
      }
      // design/171 — disk before network (survives process kill).
      final disk = await _injectFiguresFromDisk(hs);
      // Persist any RAM-only bytes (prior hydrate) onto disk.
      for (final f in hs.figures) {
        if (f.id.isEmpty || f.imageSrc.trim().isEmpty) continue;
        await _figureDisk.writeDataUrl(
          cid,
          figureId: f.id,
          imageSrc: f.imageSrc,
          contentHash: hs.contentHash,
        );
      }
      _hydrateSessions[cid] = hs;

      var filled = countFilledFromSrcList(hs.figures.map((f) => f.imageSrc));
      _figureHydrate[cid] = FigureHydrateSnapshot(
        cacheId: cid,
        phase: FigureHydratePhase.hydrating,
        total: hs.figureCount,
        filled: filled,
        failed: 0,
        attemptN: attempt,
      );
      asrEvidenceBus?.record(
        'figure_hydrate_start',
        severity: 'boundary',
        cacheId: cid,
        stage: 'hydrate_bg',
        ok: true,
        details: {
          'total': hs.figureCount,
          'filled': filled,
          'failed': 0,
          'attempt_n': attempt,
          'source':
              disk.miss == 0 && filled >= hs.figureCount ? 'disk' : 'hydrate_bg',
          'disk_hit_n': disk.hit,
          'disk_miss_n': disk.miss,
          'mode': 'per_png',
        },
      );
      notifyListeners();

      if (filled >= hs.figureCount) {
        _figureHydrate[cid] = finishHydrate(
          _figureHydrate[cid]!,
          filled: filled,
          failed: 0,
        );
        asrEvidenceBus?.record(
          'figure_hydrate_done',
          severity: 'boundary',
          cacheId: cid,
          stage: 'hydrate_bg',
          ok: true,
          details: {
            'total': hs.figureCount,
            'filled': filled,
            'failed': 0,
            'attempt_n': attempt,
            'source': 'disk',
            'disk_hit_n': disk.hit,
            'disk_miss_n': disk.miss,
            'mode': 'per_png',
          },
        );
        notifyListeners();
        return;
      }

      final hardFailed = <int>{};
      final noRetry = <int>{};
      const noRetryReasons = {
        'figure_id_not_in_meta',
        'bad_figure_id',
        'bad_cache_id',
        'bad_file_rel',
        'path_escape',
      };
      final sw = Stopwatch()..start();

      Future<void> fetchEmptyPass({required bool isRetry}) async {
        final live0 = _hydrateSessions[cid] ?? hs!;
        final indexes = _emptyFigureIndexes(live0);
        for (final index in indexes) {
          if (_hydrateDismissed.contains(cid)) return;
          if (isRetry && noRetry.contains(index)) continue;
          final live = _hydrateSessions[cid] ?? hs!;
          if (index < 0 || index >= live.figures.length) continue;
          final fig = live.figures[index];
          if (fig.imageSrc.trim().isNotEmpty) {
            hardFailed.remove(index);
            continue;
          }
          if (fig.id.isEmpty) {
            hardFailed.add(index);
            noRetry.add(index);
            continue;
          }
          try {
            final got = await _withFigureNetGate(
              () => _client.fetchFigurePng(
                cacheId: cid,
                figureId: fig.id,
                index: index,
                evidenceSource: isRetry ? 'hydrate_bg_retry' : 'hydrate_bg',
              ),
            );
            live.figures[index].imageSrc = got.dataUrl;
            if (session?.cacheId == cid &&
                index < session!.figures.length &&
                session!.figures[index].id == fig.id) {
              session!.figures[index].imageSrc = got.dataUrl;
            }
            await _figureDisk.writeDataUrl(
              cid,
              figureId: fig.id,
              imageSrc: got.dataUrl,
              contentHash: live.contentHash,
            );
            hardFailed.remove(index);
            filled =
                countFilledFromSrcList(live.figures.map((f) => f.imageSrc));
            _figureHydrate[cid] = FigureHydrateSnapshot(
              cacheId: cid,
              phase: FigureHydratePhase.hydrating,
              total: live.figureCount,
              filled: filled,
              failed: hardFailed.length,
              attemptN: attempt,
            );
            if (filled % 2 == 0 || filled >= live.figureCount) {
              asrEvidenceBus?.record(
                'figure_hydrate_progress',
                severity: 'sample',
                cacheId: cid,
                stage: isRetry ? 'hydrate_bg_retry' : 'hydrate_bg',
                ok: true,
                details: {
                  'total': live.figureCount,
                  'filled': filled,
                  'failed': hardFailed.length,
                  'index': index,
                  'attempt_n': attempt,
                  'elapsed_ms': sw.elapsedMilliseconds,
                  'source': isRetry ? 'hydrate_bg_retry' : 'hydrate_bg',
                  'mode': 'per_png',
                  'bytes_n': got.bytesN,
                },
              );
            }
            notifyListeners();
          } catch (e) {
            hardFailed.add(index);
            // design/181 — never pollute library sticky error from hydrate PNG fails.
            if (e is AsrApiException) {
              final r = e.reason.trim();
              if (noRetryReasons.contains(r)) {
                noRetry.add(index);
              }
            }
          }
          await Future<void>.delayed(const Duration(milliseconds: 40));
        }
      }

      // design/180 — empty indexes only, then one miss-only retry.
      await fetchEmptyPass(isRetry: false);
      if (!_hydrateDismissed.contains(cid)) {
        final stillEmpty = _emptyFigureIndexes(_hydrateSessions[cid] ?? hs);
        if (stillEmpty.isNotEmpty) {
          await fetchEmptyPass(isRetry: true);
        }
      }

      final liveEnd = _hydrateSessions[cid] ?? hs;
      filled = countFilledFromSrcList(liveEnd.figures.map((f) => f.imageSrc));
      // Any still-empty index counts as failed for honest partial.
      hardFailed.clear();
      final failSample = <int>[];
      for (var i = 0; i < liveEnd.figureCount; i++) {
        if (liveEnd.figures[i].imageSrc.trim().isEmpty) {
          hardFailed.add(i);
          if (failSample.length < 4) failSample.add(i);
        }
      }
      final done = finishHydrate(
        FigureHydrateSnapshot(
          cacheId: cid,
          phase: FigureHydratePhase.hydrating,
          total: liveEnd.figureCount,
          filled: filled,
          failed: hardFailed.length,
          attemptN: attempt,
        ),
        filled: filled,
        failed: hardFailed.length,
      );
      _figureHydrate[cid] = done;
      final details = <String, dynamic>{
        'total': done.total,
        'filled': done.filled,
        'failed': done.failed,
        'failed_n': done.failed,
        'attempt_n': attempt,
        'elapsed_ms': sw.elapsedMilliseconds,
        'source': 'hydrate_bg',
        'mode': 'per_png',
      };
      for (var k = 0; k < failSample.length; k++) {
        details['fail_i$k'] = failSample[k];
      }
      asrEvidenceBus?.record(
        done.phase == FigureHydratePhase.doneOk
            ? 'figure_hydrate_done'
            : 'figure_hydrate_partial',
        severity: done.phase == FigureHydratePhase.doneOk ? 'boundary' : 'error',
        cacheId: cid,
        stage: 'hydrate_bg',
        ok: done.phase == FigureHydratePhase.doneOk,
        details: details,
      );
      notifyListeners();
    } finally {
      _hydrateActive.remove(cid);
    }
  }

  /// design/169o — library 재감수 residual banner (server-driven poll).
  final Map<String, HarmonizeResidualSnapshot> _harmonizeResidual = {};
  final Map<String, Timer> _harmonizePollTimers = {};
  final Set<String> _harmonizeDismissed = {};

  String harmonizeResidualLabel(String cacheId) {
    final s = _harmonizeResidual[cacheId.trim()];
    if (s == null) return '';
    return s.userLabel;
  }

  HarmonizeResidualSnapshot? harmonizeResidualSnapshot(String cacheId) =>
      _harmonizeResidual[cacheId.trim()];

  void dismissHarmonizeResidual(String cacheId) {
    final cid = cacheId.trim();
    if (cid.isEmpty) return;
    _harmonizeDismissed.add(cid);
    _harmonizePollTimers.remove(cid)?.cancel();
    _harmonizeResidual.remove(cid);
    notifyListeners();
  }

  /// Start / restart polling paper list fields for 재감수 progress.
  void enqueueHarmonizeResidualPoll(
    String cacheId, {
    bool force = false,
    bool pendingHint = false,
    int totalHint = 0,
    int doneHint = 0,
    int failedHint = 0,
    int attemptHint = 1,
  }) {
    final cid = cacheId.trim();
    if (cid.isEmpty) return;
    if (!force && _harmonizeDismissed.contains(cid)) return;
    if (force) _harmonizeDismissed.remove(cid);
    if (!force && _harmonizePollTimers.containsKey(cid)) return;

    final fromPaper = paperEntryForCacheId(cid);
    final pending = pendingHint || (fromPaper?.harmonizePending == true);
    final total = totalHint > 0
        ? totalHint
        : (fromPaper?.harmonizeTotal ?? 0);
    final done = doneHint > 0 ? doneHint : (fromPaper?.harmonizeDone ?? 0);
    final failed =
        failedHint > 0 ? failedHint : (fromPaper?.harmonizeFailed ?? 0);
    final attempt = attemptHint > 0
        ? attemptHint
        : (fromPaper?.harmonizeAttemptN ?? 1);

    if (!pending && total < 1 && !force) {
      _harmonizeResidual.remove(cid);
      _harmonizePollTimers.remove(cid)?.cancel();
      return;
    }

    final snap = snapshotFromServerFields(
      cacheId: cid,
      pending: pending || total > done,
      total: total,
      done: done,
      failed: failed,
      attemptN: attempt,
    );
    _harmonizeResidual[cid] = snap;
    asrEvidenceBus?.record(
      'harmonize_residual_start',
      severity: 'boundary',
      cacheId: cid,
      stage: 'library_poll',
      ok: true,
      details: {
        'total': snap.total,
        'done': snap.done,
        'attempt_n': snap.attemptN,
        'source': 'client_poll_arm',
      },
    );
    notifyListeners();
    _harmonizePollTimers.remove(cid)?.cancel();
    _harmonizePollTimers[cid] = Timer.periodic(
      const Duration(seconds: 3),
      (_) => unawaited(_tickHarmonizeResidualPoll(cid)),
    );
    unawaited(_tickHarmonizeResidualPoll(cid));
  }

  Future<void> _tickHarmonizeResidualPoll(String cid) async {
    try {
      final fetched = await _client.listPapers();
      _publishPapers(await _applySavedOrder(fetched));
    } catch (_) {
      // fail-soft; keep prior snapshot
    }
    final e = paperEntryForCacheId(cid);
    if (e == null) return;
    final snap = snapshotFromServerFields(
      cacheId: cid,
      pending: e.harmonizePending,
      total: e.harmonizeTotal,
      done: e.harmonizeDone,
      failed: e.harmonizeFailed,
      attemptN: e.harmonizeAttemptN > 0 ? e.harmonizeAttemptN : 1,
    );
    final prev = _harmonizeResidual[cid];
    _harmonizeResidual[cid] = snap;
    if (prev == null ||
        prev.done != snap.done ||
        prev.phase != snap.phase) {
      if (snap.phase == HarmonizeResidualPhase.running ||
          snap.phase == HarmonizeResidualPhase.arming) {
        asrEvidenceBus?.record(
          'harmonize_residual_progress',
          severity: 'sample',
          cacheId: cid,
          stage: 'library_poll',
          ok: true,
          details: {
            'total': snap.total,
            'done': snap.done,
            'failed': snap.failed,
          },
        );
      }
    }
    if (snap.hideBanner || snap.showFailure) {
      _harmonizePollTimers.remove(cid)?.cancel();
      asrEvidenceBus?.record(
        snap.phase == HarmonizeResidualPhase.doneOk
            ? 'harmonize_residual_done'
            : (snap.phase == HarmonizeResidualPhase.aborted
                ? 'harmonize_residual_abort'
                : 'harmonize_residual_partial'),
        severity: snap.phase == HarmonizeResidualPhase.doneOk
            ? 'boundary'
            : 'error',
        cacheId: cid,
        stage: 'library_poll',
        ok: snap.phase == HarmonizeResidualPhase.doneOk,
        details: {
          'total': snap.total,
          'done': snap.done,
          'failed': snap.failed,
        },
      );
      if (snap.hideBanner) {
        _harmonizeResidual.remove(cid);
      }
    }
    notifyListeners();
  }

  UploadNotify get uploadNotify => _notify;

  Future<void> initUploadNotify() async {
    await _notify.init();
    await reconcileUploadNotify();
  }

  /// design/170 — drop orphan FGS when no in-flight upload and no resumable draft.
  Future<void> reconcileUploadNotify() async {
    if (uploading || reanalyzing) return;
    final draft = await _drafts.read();
    final resumable = draft != null &&
        (draft.canReattach || draft.canResumeChunks);
    if (resumable) return;
    await _cancelWorkmanager();
    await _notify.stop();
  }

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
    if (s.contains('번역') || s.contains('translat')) {
      return 'translate';
    }
    if (s.contains('다듬') || s.contains('debone') || s.contains('훑')) {
      return 'debone';
    }
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
    const order = [
      'prepare',
      'uploading',
      'reattach',
      'processing',
      'translate',
      'done',
    ];
    final a = order.indexOf(prev);
    final b = order.indexOf(next);
    if (a >= 0 && b >= 0) return b > a;
    return next.isNotEmpty && next != prev;
  }

  bool _isTranslateHangZone({required int percent, required String stage}) {
    final key = _hangStageKey(stage);
    // Debone Gemini chunks can exceed 180s (Turn2 hang at 다듬는 중 8/14).
    return key == 'translate' ||
        key == 'debone' ||
        percent >= 88 ||
        stage.contains('번역') ||
        stage.contains('다듬');
  }

  void _ensureHangLocalBound() {
    if (_hangLocalBound) return;
    _hangLocalBound = true;
    asrErrorReporter?.hang.setLocalHandler(_onIngestHangLocal);
  }

  /// design/134 — local fail-closed abort; cloud report runs after via HangWatchdog.
  /// 0.3.123 — translate zone: warn only, do not cancel poll.
  /// 0.3.155 — debone zone: same soft hang (long Gemini chunk).
  void _onIngestHangLocal(String opId, String kind) {
    if (_hangOpId == null || opId != _hangOpId) return;
    final translateZone = _isTranslateHangZone(
      percent: _hangLastPercent,
      stage: uploadStage.isNotEmpty ? uploadStage : _hangLastStageKey,
    );
    asrEvidenceBus?.record(
      'client_hang',
      severity: 'error',
      stage: translateZone ? 'translate' : _hangLastStageKey,
      percent: _hangLastPercent < 0 ? null : _hangLastPercent,
      message: translateZone
          ? 'translate hang soft'
          : 'ingest hang abort',
      ok: false,
      details: {
        'translate_zone': translateZone,
        'cancel': !translateZone,
      },
    );
    if (translateZone) {
      final debone = _hangStageKey(uploadStage).contains('debone') ||
          uploadStage.contains('다듬');
      error = debone
          ? '다듬기가 오래 걸리고 있습니다. 잠시만 기다려 주세요.'
          : '번역이 오래 걸리고 있습니다. 잠시 후 보관함을 새로고침해 주세요.';
      uploadStage = error!;
      notifyListeners();
      unawaited(_notify.showFailed(message: error!));
      // Re-arm so a later true stall can warn again; poll keeps running.
      asrErrorReporter?.hang.begin(
        opId,
        stage: debone ? 'debone' : 'translate',
        stallAfter: HangWatchdog.translateStall,
        paperTitle: uploadStage,
      );
      _hangTranslateStallArmed = true;
      return;
    }
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
    _hangLastMessage = '';
    _hangTranslateStallArmed = false;
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
  /// 0.3.123 — message change counts (translate can sit at 90%).
  void _noteIngestHangProgress({required int percent, required String stage}) {
    final op = _hangOpId;
    if (op == null) return;
    final key = _hangStageKey(stage);
    final pct = percent.clamp(0, 100);
    final msg = stage.trim();
    final pctUp = pct > _hangLastPercent;
    final stageUp = _hangStageForward(key, _hangLastStageKey);
    final msgUp = msg.isNotEmpty && msg != _hangLastMessage;
    if (!pctUp && !stageUp && !msgUp) {
      // Same place — leave stall timer running (do not noteRepeat every poll).
      return;
    }
    _hangLastPercent = pct;
    _hangLastMessage = msg;
    if (stageUp || _hangLastStageKey.isEmpty) {
      _hangLastStageKey = key;
    }
    if (_isTranslateHangZone(percent: pct, stage: stage) &&
        !_hangTranslateStallArmed) {
      asrErrorReporter?.hang.setStallAfter(op, HangWatchdog.translateStall);
      _hangTranslateStallArmed = true;
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

  /// design/75 · 195 — call from HomeShell on AppLifecycleState.resumed.
  Future<IngestJobResult?> onAppResumed() async {
    // design/195 — always try unfinished KO/shadowing when app returns.
    unawaited(scanAndEnqueuePendingEnrich(trigger: 'app_resume'));
    // design/238 · 242 — rescan connected PDF folder (find-watch + new downloads).
    unawaited(rescanPdfFolderDebounced(trigger: 'app_resume'));
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


  bool _bulkHandoffRunning = false;
  bool _bulkHandoffAttempted = false;

  /// design/185 J21 — one-shot pull of cloud papers missing a local session.
  Future<void> handoffRemoteLibraryIfNeeded({bool force = false}) async {
    if (_bulkHandoffRunning) return;
    if (_bulkHandoffAttempted && !force) return;
    if (!_paperDisk.isBound || papers.isEmpty) return;
    if (opening || uploading || reanalyzing) return;
    try {
      final st = await _client.fetchStatus();
      if (!st.paperHandoff || !st.paperLocalSot) return;
    } catch (_) {
      return;
    }
    final targets = <PaperEntry>[
      for (final e in papers)
        if (e.id.trim().isNotEmpty &&
            e.ingestStatus != 'local' &&
            !(await _paperDisk.hasSession(e.id)))
          e,
    ];
    if (targets.isEmpty) {
      _bulkHandoffAttempted = true;
      return;
    }
    _bulkHandoffRunning = true;
    _bulkHandoffAttempted = true;
    asrEvidenceBus?.record(
      'paper_bulk_handoff_start',
      severity: 'lifecycle',
      stage: 'client',
      ok: true,
      details: {'n': targets.length},
    );
    var okN = 0;
    var failN = 0;
    try {
      for (final e in targets) {
        if (opening || uploading || reanalyzing) break;
        final ok = await _runPaperHandoff(e.id, title: e.title);
        if (ok) {
          okN += 1;
        } else {
          failN += 1;
        }
      }
    } finally {
      _bulkHandoffRunning = false;
      asrEvidenceBus?.record(
        'paper_bulk_handoff_done',
        severity: 'lifecycle',
        stage: 'client',
        ok: failN == 0,
        details: {'ok_n': okN, 'fail_n': failN, 'target_n': targets.length},
      );
      if (okN > 0) {
        await refresh();
      }
      notifyListeners();
    }
  }

  Future<List<Map<String, dynamic>>?> _shadowingSentencesPayload(
    String cacheId,
  ) async {
    final cid = cacheId.trim();
    if (cid.isEmpty) return null;
    List<dynamic>? rows;
    if (session != null &&
        session!.cacheId.trim() == cid &&
        session!.sentences.isNotEmpty) {
      rows = session!.sentences;
    } else {
      final raw = await _paperDisk.loadSessionJson(cid);
      final sents = raw == null ? null : raw['sentences'];
      if (sents is List && sents.isNotEmpty) {
        final out = <Map<String, dynamic>>[];
        for (final item in sents) {
          if (item is! Map) continue;
          final id = '${item['id'] ?? ''}'.trim();
          final text = '${item['text'] ?? ''}'.trim();
          if (text.isEmpty) continue;
          out.add({
            'id': id.isEmpty ? '${out.length}' : id,
            'text': text,
          });
        }
        return out.isEmpty ? null : out;
      }
      return null;
    }
    return [
      for (var i = 0; i < rows.length; i++)
        {
          'id': rows[i].id.trim().isEmpty ? '$i' : rows[i].id,
          'text': rows[i].text,
        },
    ];
  }

  /// design/185 — pull paper folder chunks, verify sha256, ACK (may wipe cloud).
  Future<bool> _runPaperHandoff(String cacheId, {String title = ''}) async {
    final cid = cacheId.trim();
    if (cid.isEmpty || !_paperDisk.isBound) return false;
    try {
      final st = await _client.fetchStatus();
      if (!st.paperHandoff) return false;
    } catch (_) {
      // Missing status → skip handoff (fail-soft); cloud library still works.
      return false;
    }
    try {
      asrEvidenceBus?.record(
        'paper_handoff_start',
        severity: 'lifecycle',
        cacheId: cid,
        stage: 'client_pull',
        ok: true,
      );
      final manifest = await _client.getHandoffManifest(cid);
      if (manifest['ok'] != true) {
        final err = '${manifest['error'] ?? ''}';
        if (err == 'already_acked') {
          return await _paperDisk.hasSession(cid);
        }
        return false;
      }
      final filesRaw = manifest['files'];
      if (filesRaw is! Map) return false;
      final contentHash = '${manifest['content_hash'] ?? ''}'.trim().toLowerCase();
      final artifactGen = '${manifest['artifact_gen'] ?? ''}'.trim();
      final titleM = '${manifest['title'] ?? title}'.trim();
      if (contentHash.isNotEmpty) {
        await _paperDisk.ensureContentHash(cid, contentHash);
      }
      var okN = 0;
      for (final e in filesRaw.entries) {
        final rel = '${e.key}'.trim();
        if (rel.isEmpty || e.value is! Map) continue;
        final meta = Map<String, dynamic>.from(e.value as Map);
        final wantSha = '${meta['sha256'] ?? ''}'.trim().toLowerCase();
        final bytes = await _client.getHandoffFile(cid, rel);
        if (wantSha.isNotEmpty &&
            paperDiskSha256Hex(bytes) != wantSha) {
          asrEvidenceBus?.record(
            'paper_handoff_done',
            severity: 'error',
            cacheId: cid,
            stage: 'sha_mismatch',
            ok: false,
            details: {'rel': rel.length > 40 ? rel.substring(0, 40) : rel},
          );
          return false;
        }
        final wrote = await _paperDisk.applyHandoffFile(
          cid,
          rel,
          bytes,
          contentHash: contentHash,
        );
        if (!wrote) return false;
        okN += 1;
      }
      if (okN < 1) return false;
      final ack = await _client.postHandoffAck(
        cid,
        contentHash: contentHash,
        artifactGen: artifactGen,
        fileCount: okN,
      );
      if (ack['ok'] != true) return false;
      await _paperDisk.upsertIndex(
        PaperDiskIndexEntry(
          id: cid,
          title: titleM.isEmpty ? cid : titleM,
          updatedAt: DateTime.now().toUtc().toIso8601String(),
          contentHash: contentHash,
          hasSource: false,
          docRole: () {
            for (final e in papers) {
              if (e.id == cid && e.docRole.isNotEmpty) return e.docRole;
            }
            return 'main';
          }(),
        ),
      );
      // Refresh sentence/figure counts from session if present.
      final session = await _paperDisk.loadSessionJson(cid);
      if (session != null) {
        final sents = session['sentences'];
        final figs = session['figures'];
        final roleRaw = '${session['doc_role'] ?? ''}'.trim().toLowerCase();
        final role = (roleRaw == 'supplementary' ||
                roleRaw == 'si' ||
                roleRaw == 'supp')
            ? 'supplementary'
            : (roleRaw == 'merged' ? 'merged' : 'main');
        // Prefer role from live library row when session omitted it.
        final roleFinal = () {
          if (role != 'main') return role;
          for (final e in papers) {
            if (e.id == cid && e.docRole.isNotEmpty) return e.docRole;
          }
          return role;
        }();
        await _paperDisk.upsertIndex(
          PaperDiskIndexEntry(
            id: cid,
            title: titleM.isEmpty
                ? '${session['title'] ?? cid}'.trim()
                : titleM,
            updatedAt: DateTime.now().toUtc().toIso8601String(),
            sentenceCount: sents is List ? sents.length : 0,
            figureCount: figs is List ? figs.length : 0,
            contentHash: contentHash,
            hasSource: true,
            docRole: roleFinal,
          ),
        );
      }
      asrEvidenceBus?.record(
        'paper_handoff_done',
        severity: 'lifecycle',
        cacheId: cid,
        stage: ack['wiped'] == true ? 'wiped' : 'acked',
        ok: true,
        details: {
          'file_n': okN,
          'wiped': ack['wiped'] == true ? 1 : 0,
        },
      );
      // design/194 — KO backfill + shadowing after handoff (library tab, not only reader).
      unawaited(_postHandoffEnrich(cid));
      return true;
    } catch (e) {
      asrEvidenceBus?.record(
        'paper_handoff_done',
        severity: 'error',
        cacheId: cid,
        stage: 'fail',
        ok: false,
        message: e.toString().length > 160 ? e.toString().substring(0, 160) : e.toString(),
      );
      return false;
    }
  }

  /// design/194·195 — after handoff: enqueue KO + shadowing.
  Future<void> _postHandoffEnrich(String cacheId) async {
    enqueuePendingEnrich(cacheId, trigger: 'handoff', force: true);
  }

  void _clearPendingEnrichState() {
    _enrichRetryTimer?.cancel();
    _enrichRetryTimer = null;
    _enrichQueue.clear();
    _enrichInQueue.clear();
    _enrichFailCount.clear();
    _enrichLoopBusy = false;
    pendingEnrichBusy = false;
    pendingEnrichCacheId = null;
    pendingEnrichTrigger = null;
  }

  /// design/195 — queue unfinished translate/shadowing for one paper.
  void enqueuePendingEnrich(
    String cacheId, {
    String trigger = 'manual',
    bool force = false,
  }) {
    final cid = cacheId.trim();
    if (cid.isEmpty || !_paperDisk.isBound) return;
    final trig = trigger.trim().isEmpty ? 'manual' : trigger.trim();
    if (!force && _enrichInQueue.contains(cid)) return;
    if (!force && pendingEnrichCacheId == cid && _enrichLoopBusy) return;
    if (!_enrichInQueue.contains(cid)) {
      _enrichInQueue.add(cid);
      _enrichQueue.add(cid);
    }
    asrEvidenceBus?.record(
      'pending_enrich_enqueue',
      severity: 'decision',
      cacheId: cid,
      stage: trig.length > 40 ? trig.substring(0, 40) : trig,
      ok: true,
      details: {
        'force': force ? 1 : 0,
        'queue_n': _enrichQueue.length,
        'fail_n': _enrichFailCount[cid] ?? 0,
      },
    );
    pendingEnrichBusy = true;
    notifyListeners();
    unawaited(_pumpPendingEnrichQueue(defaultTrigger: trig));
  }
  /// design/195 — scan local papers for unfinished KO / shadowing.
  Future<void> scanAndEnqueuePendingEnrich({
    String trigger = 'boot',
  }) async {
    if (!_paperDisk.isBound) return;
    if (papers.isEmpty) return;
    final trig = trigger.trim().isEmpty ? 'boot' : trigger.trim();
    var needKo = 0;
    var needSh = 0;
    var scanned = 0;
    final wantTr = await _wantTranslate();
    final wantSh = await _wantShadowingPractice();
    for (final p in papers) {
      final cid = p.id.trim();
      if (cid.isEmpty) continue;
      if (!await _paperDisk.hasSession(cid)) continue;
      scanned += 1;
      final needs = await _pendingEnrichNeeds(cid, wantTr: wantTr, wantSh: wantSh);
      if (needs.ko) needKo += 1;
      if (needs.sh) needSh += 1;
      if (needs.ko || needs.sh) {
        enqueuePendingEnrich(cid, trigger: trig);
      }
    }
    asrEvidenceBus?.record(
      'pending_enrich_scan',
      severity: 'lifecycle',
      stage: trig.length > 40 ? trig.substring(0, 40) : trig,
      ok: true,
      details: {
        'scanned_n': scanned,
        'need_ko_n': needKo,
        'need_shadowing_n': needSh,
        'queue_n': _enrichQueue.length,
      },
    );
  }

  Future<({bool ko, bool sh})> _pendingEnrichNeeds(
    String cacheId, {
    required bool wantTr,
    required bool wantSh,
  }) async {
    var ko = false;
    var sh = false;
    if (wantTr) {
      final raw = await _paperDisk.loadSessionJson(cacheId);
      if (raw != null) {
        final pending = raw['translate_pending'] == true;
        var missing = 0;
        final sents = raw['sentences'];
        if (sents is List) {
          for (final item in sents) {
            if (item is! Map) continue;
            final text = (item['text']?.toString() ?? '').trim();
            final koText = (item['text_ko']?.toString() ?? '').trim();
            if (text.isNotEmpty && koText.isEmpty) missing += 1;
          }
        }
        ko = pending || missing > 0;
      }
    }
    if (wantSh) {
      final plan = await _shadowDisk.loadChunkPlanJson(cacheId);
      final st = plan == null ? '' : (plan['status']?.toString() ?? '').trim();
      sh = st != 'ok';
    }
    return (ko: ko, sh: sh);
  }

  Future<void> _pumpPendingEnrichQueue({String defaultTrigger = 'boot'}) async {
    if (_enrichLoopBusy) return;
    _enrichLoopBusy = true;
    pendingEnrichBusy = true;
    notifyListeners();
    try {
      while (_enrichQueue.isNotEmpty) {
        final cid = _enrichQueue.removeAt(0);
        _enrichInQueue.remove(cid);
        pendingEnrichCacheId = cid;
        pendingEnrichTrigger = defaultTrigger;
        notifyListeners();
        await _runPendingEnrich(cid, trigger: defaultTrigger);
      }
    } finally {
      _enrichLoopBusy = false;
      pendingEnrichCacheId = null;
      pendingEnrichTrigger = null;
      pendingEnrichBusy = _enrichQueue.isNotEmpty || _enrichRetryTimer != null;
      notifyListeners();
      if (_enrichQueue.isNotEmpty) {
        unawaited(_pumpPendingEnrichQueue(defaultTrigger: defaultTrigger));
      }
    }
  }

  Future<void> _runPendingEnrich(
    String cacheId, {
    required String trigger,
  }) async {
    final cid = cacheId.trim();
    if (cid.isEmpty) return;
    final wantTr = await _wantTranslate();
    final wantSh = await _wantShadowingPractice();
    final needs = await _pendingEnrichNeeds(cid, wantTr: wantTr, wantSh: wantSh);
    if (!needs.ko && !needs.sh) {
      _enrichFailCount.remove(cid);
      asrEvidenceBus?.record(
        'pending_enrich_done',
        severity: 'lifecycle',
        cacheId: cid,
        stage: trigger,
        ok: true,
        details: {'skipped': 1, 'reason': 'already_ok'},
      );
      return;
    }
    asrEvidenceBus?.record(
      'pending_enrich_start',
      severity: 'lifecycle',
      cacheId: cid,
      stage: trigger,
      ok: true,
      details: {
        'need_ko': needs.ko ? 1 : 0,
        'need_shadowing': needs.sh ? 1 : 0,
        'fail_n': _enrichFailCount[cid] ?? 0,
      },
    );
    var koOk = !needs.ko;
    var shOk = !needs.sh;
    try {
      if (needs.ko) {
        await _backfillLocalMissingKoFromDisk(cid);
        final after = await _pendingEnrichNeeds(cid, wantTr: wantTr, wantSh: false);
        koOk = !after.ko;
      }
    } catch (_) {
      koOk = false;
    }
    try {
      if (needs.sh) {
        await ensureShadowingChunks(cid, trigger: 'pending_enrich');
        shOk = shadowingChunksError == null;
        if (shOk) {
          final after = await _pendingEnrichNeeds(cid, wantTr: false, wantSh: true);
          shOk = !after.sh;
        }
      }
    } catch (_) {
      shOk = false;
    }
    final ok = koOk && shOk;
    asrEvidenceBus?.record(
      'pending_enrich_done',
      severity: 'lifecycle',
      cacheId: cid,
      stage: trigger,
      ok: ok,
      details: {
        'ko_ok': koOk ? 1 : 0,
        'shadowing_ok': shOk ? 1 : 0,
        'fail_n': _enrichFailCount[cid] ?? 0,
      },
    );
    if (ok) {
      _enrichFailCount.remove(cid);
      return;
    }
    final fails = (_enrichFailCount[cid] ?? 0) + 1;
    _enrichFailCount[cid] = fails;
    if (fails >= kPendingEnrichMaxRetries) {
      asrEvidenceBus?.record(
        'pending_enrich_give_up',
        severity: 'error',
        cacheId: cid,
        stage: trigger,
        ok: false,
        details: {'fail_n': fails},
      );
      return;
    }
    final delaySec = 5 * fails * fails;
    asrEvidenceBus?.record(
      'pending_enrich_retry',
      severity: 'boundary',
      cacheId: cid,
      stage: trigger,
      ok: true,
      details: {'fail_n': fails, 'delay_s': delaySec},
    );
    _enrichRetryTimer?.cancel();
    _enrichRetryTimer = Timer(Duration(seconds: delaySec), () {
      _enrichRetryTimer = null;
      enqueuePendingEnrich(cid, trigger: 'retry', force: true);
    });
    pendingEnrichBusy = true;
    notifyListeners();
  }


  /// design/174 — after ingest/reanalyze: refresh, then fresh=1 once; emit on miss.
  Future<bool> _confirmCacheInLibrary(
    String cacheId, {
    String jobId = '',
    String stage = 'after_ingest',
  }) async {
    final cid = cacheId.trim();
    if (cid.isEmpty) return false;
    await refresh();
    if (papers.any((p) => p.id == cid)) return true;
    if (await _paperDisk.hasSession(cid)) {
      await refresh(fresh: true);
      if (papers.any((p) => p.id == cid)) return true;
      return true; // local SoT after wipe — list merge may lag one frame
    }
    await refresh(fresh: true);
    final seen = papers.any((p) => p.id == cid);
    if (!seen) {
      asrEvidenceBus?.record(
        'library_list_miss',
        severity: 'consistency',
        cacheId: cid,
        jobId: jobId,
        ok: false,
        stage: stage.length > 40 ? stage.substring(0, 40) : stage,
        details: {'paper_n': papers.length},
      );
    }
    return seen;
  }


  /// design/179 — after ingest poll failure, still pull GCS library (sticky error kept).
  Future<void> _refreshLibraryAfterIngestFail() async {
    try {
      await refresh(
        fresh: true,
        clearError: false,
        trigger: 'after_ingest_fail',
      );
    } catch (_) {
      // sticky error already set by caller
    }
  }

  Future<void> refresh({
    bool fresh = false,
    bool clearError = true,
    String trigger = 'manual',
  }) async {
    loading = true;
    if (clearError) {
      error = null;
    }
    notifyListeners();
    final trig = trigger.trim().isEmpty ? 'manual' : trigger.trim();
    try {
      final fetched = await _client.listPapers(fresh: fresh);
      // design/222 — persist server doc_role/content_hash onto disk index before wipe.
      for (final e in fetched) {
        if (e.id.isEmpty) continue;
        try {
          await _paperDisk.upsertIndex(
            PaperDiskIndexEntry(
              id: e.id,
              title: e.title.isEmpty ? e.id : e.title,
              source: e.source,
              updatedAt: e.updatedAt,
              sentenceCount: e.sentenceCount,
              figureCount: e.figureCount,
              contentHash: e.contentHash,
              pipelineVersion: e.pipelineVersion,
              hasSource: e.hasSource,
              debone: e.debone,
              docRole: e.docRole,
              pairedCacheId: e.pairedCacheId,
              canMergeSupplementary: e.canMergeSupplementary,
            ),
          );
        } catch (_) {}
      }
      // design/185 Phase 1 — surface local-only disk papers (no cloud wipe yet).
      final merged = await _paperDisk.mergeRemoteWithLocal(fetched);
      _publishPapers(await _applySavedOrder(merged));
      await _rebuildLibraryHashSet();
      await _reloadPickerRecent();
      try {
        final uid = await _authUid();
        progressResumeByCacheId = await loadProgressResumeLabels(
          uid: uid,
          cacheIds: papers.map((e) => e.id),
        );
      } catch (_) {
        // EDGE: resume labels optional for library list.
      }
      final n = papers.length;
      // design/169d — always on fail path; sample success 1/5 via count emit.
      // design/179 — trigger + preserved_error for after_ingest_fail join.
      asrEvidenceBus?.record(
        'library_refresh',
        severity: 'lifecycle',
        stage: fresh ? 'ok_fresh' : 'ok',
        ok: true,
        details: {
          'paper_n': n,
          'fresh': fresh ? 1 : 0,
          'trigger': trig,
          if (!clearError) 'preserved_error': 1,
        },
      );
      asrEvidenceBus?.record(
        'library_count',
        severity: 'boundary',
        stage: 'refresh',
        ok: true,
        details: {'paper_n': n, 'trigger': trig},
      );
      // design/185 J21 — migrate pre-existing cloud papers once per bind.
      unawaited(handoffRemoteLibraryIfNeeded());
      if (_shadowingLocalSot) {
        unawaited(
          migrateShadowingCloudOnce(
            client: _client,
            uid: _diskUid,
            cacheIds: papers.map((e) => e.id).toList(growable: false),
          ),
        );
      }
    } on AsrApiException catch (e) {
      if (clearError) {
        error = e.message;
      }
      papers = const [];
      asrEvidenceBus?.record(
        'library_refresh',
        severity: 'error',
        stage: 'fail',
        ok: false,
        httpStatus: e.statusCode,
        message: e.message.length > 200 ? e.message.substring(0, 200) : e.message,
        details: {
          'paper_n': 0,
          'trigger': trig,
          if (!clearError) 'preserved_error': 1,
        },
      );
    } on TimeoutException catch (e) {
      // design/159 — keep last good list; server may still complete after app gave up.
      if (clearError) {
        error = '서버 응답이 느립니다. 잠시 후 새로고침해 주세요.';
      }
      asrEvidenceBus?.record(
        'client_api_timeout',
        severity: 'error',
        route: 'library_list',
        stage: 'library_refresh',
        message: e.toString().length > 200 ? e.toString().substring(0, 200) : e.toString(),
        ok: false,
      );
    } catch (e) {
      if (clearError) {
        error = e.toString();
      }
      papers = const [];
      asrEvidenceBus?.record(
        'library_refresh',
        severity: 'error',
        stage: 'fail',
        ok: false,
        message: error!.length > 200 ? error!.substring(0, 200) : error!,
      );
    } finally {
      loading = false;
      notifyListeners();
      unawaited(_refreshResumeOffer());
      unawaited(hydrateUploadQueue(pump: true));
      unawaited(refreshReadLeftTimes());
      unawaited(
        _editStash.purgeOrphans(papers.map((p) => p.id).toSet()),
      );
      unawaited(reconcileUploadNotify());
      for (final p in papers) {
        if (p.harmonizePending) {
          enqueueHarmonizeResidualPoll(p.id);
        }
      }
      // design/195 — unfinished KO/shadowing resume after library is visible.
      unawaited(scanAndEnqueuePendingEnrich(trigger: 'library_refresh'));
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
    _publishPapers(next);
    notifyListeners();
    await _persistOrder(papers.map((e) => e.id).toList(growable: false));
  }

  /// design/102 + design/177 — delete selected papers (GCS + user records via API).
  /// Honesty: list rows are removed only after HTTP ok for that id.
  Future<int> deletePapers(Iterable<String> cacheIds) async {
    final ids = cacheIds
        .map((e) => e.trim())
        .where((e) => e.isNotEmpty)
        .toSet()
        .toList(growable: false);
    if (ids.isEmpty) return 0;
    var okCount = 0;
    final okIds = <String>{};
    String? lastErr;
    for (final id in ids) {
      final sw = Stopwatch()..start();
      final hid = asrEvidenceBus?.recordHandoff(
            fromStage: 'client_delete',
            toStage: 'server_delete',
            cacheId: id,
            stage: 'delete',
          ) ??
          'hf_${DateTime.now().microsecondsSinceEpoch.toRadixString(16)}';
      asrEvidenceBus?.record(
        'paper_delete_start',
        severity: 'lifecycle',
        cacheId: id,
        stage: 'start',
        ok: true,
        details: {
          'handoff_id': hid,
          'timeout_ms': 60000,
          'selected_n': ids.length,
        },
      );
      try {
        await _client.deletePaper(id, handoffId: hid);
        okCount += 1;
        okIds.add(id);
        asrEvidenceBus?.record(
          'paper_delete_done',
          severity: 'lifecycle',
          cacheId: id,
          stage: 'ok',
          ok: true,
          code: 'ok',
          details: {
            'handoff_id': hid,
            'elapsed_ms': sw.elapsedMilliseconds,
          },
        );
        asrEvidenceBus?.record(
          'paper_delete',
          severity: 'lifecycle',
          cacheId: id,
          stage: 'ok',
          ok: true,
          details: {
            'handoff_id': hid,
            'elapsed_ms': sw.elapsedMilliseconds,
          },
        );
        await _editStash.purge(id);
        await _figureDisk.purge(id);
        await _paperDisk.purge(id);
        await _shadowDisk.purge(id);
        _hydrateSessions.remove(id);
        _figureHydrate.remove(id);
        _hydrateDismissed.remove(id);
        await _bookmarks?.purgePaper(id);
        if (session?.cacheId == id) {
          clearOpened();
        }
      } on TimeoutException catch (e) {
        lastErr = '삭제가 시간 초과되었습니다. 서버가 바쁠 수 있으니 잠시 후 새로고침해 주세요.';
        asrEvidenceBus?.record(
          'paper_delete_done',
          severity: 'error',
          cacheId: id,
          stage: 'timeout',
          ok: false,
          code: 'timeout',
          message: e.toString().length > 200 ? e.toString().substring(0, 200) : e.toString(),
          details: {
            'handoff_id': hid,
            'elapsed_ms': sw.elapsedMilliseconds,
            'timeout_ms': 60000,
          },
        );
        asrEvidenceBus?.record(
          'paper_delete',
          severity: 'error',
          cacheId: id,
          stage: 'timeout',
          ok: false,
          code: 'timeout',
          message: lastErr!,
          details: {
            'handoff_id': hid,
            'elapsed_ms': sw.elapsedMilliseconds,
          },
        );
      } on AsrApiException catch (e) {
        lastErr = e.message;
        asrEvidenceBus?.record(
          'paper_delete_done',
          severity: 'error',
          cacheId: id,
          stage: 'http_fail',
          ok: false,
          httpStatus: e.statusCode,
          code: 'http_fail',
          message: e.message.length > 200 ? e.message.substring(0, 200) : e.message,
          details: {
            'handoff_id': hid,
            'elapsed_ms': sw.elapsedMilliseconds,
          },
        );
        asrEvidenceBus?.record(
          'paper_delete',
          severity: 'error',
          cacheId: id,
          stage: 'fail',
          ok: false,
          httpStatus: e.statusCode,
          message: e.message.length > 200 ? e.message.substring(0, 200) : e.message,
          details: {
            'handoff_id': hid,
            'elapsed_ms': sw.elapsedMilliseconds,
          },
        );
      } catch (e) {
        lastErr = e.toString();
        asrEvidenceBus?.record(
          'paper_delete_done',
          severity: 'error',
          cacheId: id,
          stage: 'error',
          ok: false,
          code: 'error',
          message: lastErr!.length > 200 ? lastErr!.substring(0, 200) : lastErr!,
          details: {
            'handoff_id': hid,
            'elapsed_ms': sw.elapsedMilliseconds,
          },
        );
        asrEvidenceBus?.record(
          'paper_delete',
          severity: 'error',
          cacheId: id,
          stage: 'fail',
          ok: false,
          message: lastErr!.length > 200 ? lastErr!.substring(0, 200) : lastErr!,
          details: {
            'handoff_id': hid,
            'elapsed_ms': sw.elapsedMilliseconds,
          },
        );
      }
    }
    // design/177 J6 — only drop rows that actually deleted on the server.
    if (okIds.isNotEmpty) {
      _publishPapers(
        papers.where((p) => !okIds.contains(p.id)).toList(growable: false),
      );
      await _persistOrder(papers.map((e) => e.id).toList(growable: false));
    }
    error = okCount == ids.length
        ? null
        : (lastErr ?? '삭제에 실패했습니다.');
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
  /// design/168f H1.5 — persist job draft so 504 can resume poll (upload parity).
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
    resumeOfferVisible = false;
    notifyListeners();
    try {
      final wantTr = await _wantTranslate();
      final uid = await _authUid();
      asrEvidenceBus?.record(
        'reanalyze_pref_snapshot',
        severity: 'decision',
        cacheId: entry.id,
        details: {
          'want_translate_pref': wantTr,
          'want_translate_sent': wantTr,
          'auth_uid_present': uid != null && uid.isNotEmpty,
          'prefs_key_suffix_len': (uid ?? '').length,
        },
      );
      final started = await _client.startReanalyze(
        entry.id,
        translate: wantTr,
      );
      // Stable draft key without inventing PDF bytes.
      final hash = sha256Hex(
        Uint8List.fromList(utf8.encode('reanalyze:${entry.id}')),
      );
      final draft = UploadDraft(
        contentHash: hash,
        filename: entry.title.trim().isEmpty ? 'reanalyze' : entry.title.trim(),
        jobId: started.jobId,
        phase: 'processing',
        cacheId: entry.id,
        purpose: 'reanalyze',
      );
      await _drafts.write(draft);
      _activeJobId = started.jobId;
      await _beginIngestHang(filename: draft.filename);
      final result = await _client.pollIngestJob(
        jobId: started.jobId,
        onProgress: (pct, msg) {
          uploadPercent = pct.clamp(0, 100);
          uploadStage = msg.isEmpty ? '재분석 중' : msg;
          _noteIngestStageProgress(uploadStage, percent: uploadPercent);
          _noteIngestHangProgress(percent: uploadPercent, stage: uploadStage);
          notifyListeners();
        },
      );
      _endIngestHang();
      await _drafts.clear();
      _autoResumeGate.reset();
      if (result.cacheId.isEmpty) {
        error = '재분석은 끝났지만 보관함에 반영되지 않았습니다.';
        notifyListeners();
        return false;
      }
      await _runPaperHandoff(result.cacheId, title: result.title);
      final seen = await _confirmCacheInLibrary(
        result.cacheId,
        jobId: result.jobId,
        stage: 'after_reanalyze',
      );
      if (!seen) {
        error = '재분석은 끝났지만 목록에 아직 없습니다. 새로고침해 주세요.';
        notifyListeners();
        return false;
      }
      enqueueFigureHydrate(result.cacheId);
      enqueueHarmonizeResidualPoll(
        result.cacheId,
        pendingHint: result.harmonizePending,
        totalHint: result.harmonizeTotal,
        doneHint: result.harmonizeDone,
        failedHint: result.harmonizeFailed,
        attemptHint: result.harmonizeAttemptN > 0 ? result.harmonizeAttemptN : 1,
      );
      // WHY: 재분석 후 읽기 탭에 옛 session이 남지 않게 최신 /open 반영.
      if (session?.cacheId == entry.id || session?.cacheId == result.cacheId) {
        final openEntry = paperEntryForCacheId(result.cacheId) ?? entry;
        await open(openEntry);
      }
      await _editStash.invalidatePreviews(entry.id);
      error = null;
      lastIngestFailure = null;
      notifyListeners();
      return true;
    } on TimeoutException catch (e) {
      _endIngestHang();
      final stage = uploadStage.trim();
      error = stage.isNotEmpty
          ? '서버 응답이 느립니다. ($stage)'
          : '서버 응답이 느립니다. 「이어서 분석하기」를 눌러 주세요.';
      _pendingAutoResume = _armAutoResumeAfterTimeout(stageHint: stage);
      if (!_pendingAutoResume) {
        resumeOfferVisible = await _draftResumable();
      }
      asrEvidenceBus?.record(
        'client_api_timeout',
        severity: 'error',
        route: 'reanalyze_poll',
        cacheId: entry.id,
        message: e.toString().length > 200 ? e.toString().substring(0, 200) : e.toString(),
        ok: false,
      );
      lastIngestFailure = error;
      notifyListeners();
      return false;
    } on AsrApiException catch (e) {
      _endIngestHang();
      if (e.statusCode == 504) {
        final stage = uploadStage.trim();
        _pendingAutoResume = _armAutoResumeAfterTimeout(stageHint: stage);
        if (!_pendingAutoResume) {
          resumeOfferVisible = await _draftResumable();
        }
      } else if (e.statusCode == 409 ||
          e.statusCode == 404 ||
          e.statusCode == 422) {
        await _drafts.clear();
        resumeOfferVisible = false;
        _autoResumeGate.reset();
        _pendingAutoResume = false;
      }
      final jid = (_activeJobId ?? '').trim();
      error = e.message;
      lastIngestFailure = jid.isEmpty
          ? e.message
          : '${e.message} (job $jid)';
      notifyListeners();
      return false;
    } catch (e) {
      _endIngestHang();
      error = e.toString();
      lastIngestFailure = error;
      notifyListeners();
      return false;
    } finally {
      reanalyzing = false;
      reanalyzingCacheId = null;
      uploadPercent = 0;
      uploadStage = '';
      notifyListeners();
      if (_pendingAutoResume) {
        _schedulePendingAutoResume();
      } else {
        unawaited(_refreshResumeOffer());
      }
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
      asrEvidenceBus?.record(
        'client_api_fail',
        severity: 'error',
        route: 'merge_supplementary',
        cacheId: entry.id,
        stage: 'merge',
        httpStatus: e.statusCode,
        message: e.message.length > 200 ? e.message.substring(0, 200) : e.message,
        ok: false,
      );
      notifyListeners();
      return false;
    } catch (e) {
      error = e.toString();
      asrEvidenceBus?.record(
        'client_api_fail',
        severity: 'error',
        route: 'merge_supplementary',
        cacheId: entry.id,
        stage: 'merge',
        message: error!.length > 200 ? error!.substring(0, 200) : error!,
        ok: false,
      );
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
      final header = s.sectionNav.headerPartsFor(s.sentenceIndex);
      final sectionLabel =
          '${header.sectionName} ${header.rightLabel}'.trim();
      await saveProgressRow(
        uid: uid,
        cacheId: s.cacheId,
        sentenceIndex: s.sentenceIndex,
        figureIndex: s.figureIndex,
        layoutMode: readerLayoutMode,
        sectionLabel: sectionLabel,
      );
      final next = Map<String, String>.from(progressResumeByCacheId);
      // design/196 — section only; UI joins metaLine + section + reading mark.
      next[s.cacheId] = sectionLabel;
      progressResumeByCacheId = next;
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
    // Product: ingest quality banner hidden (warnings still persist in session).
    showIngestQualityBanner = false;
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
    // design/188 — partial KO must still backfill (old gate used hasAnyTranslation).
    if (!o.needsTranslationBackfill) return;
    unawaited(_wantTranslate().then((wantTr) async {
      if (!wantTr) return;
      if (session?.cacheId != o.cacheId) return;
      if (!o.needsTranslationBackfill) return;

      // Prefer device batch fill when local disk already owns the session.
      final localOwned = await _paperDisk.hasSession(o.cacheId);
      if (localOwned || o.translationMissingCount > 0) {
        await _backfillLocalMissingKo(o);
        return;
      }

      translateBackfillBusy = true;
      notifyListeners();
      asrEvidenceBus?.record(
        'translate_poll_start',
        severity: 'lifecycle',
        cacheId: o.cacheId,
        stage: 'translate_poll',
        ok: true,
        details: {
          'translate_pending': o.translatePending,
          'ko_sentence_n':
              o.sentences.where((s) => s.textKo.trim().isNotEmpty).length,
          'ko_missing_n': o.translationMissingCount,
        },
      );
      var attempts = 0;
      var pollErrorReported = false;
      var lastKoN =
          o.sentences.where((s) => s.textKo.trim().isNotEmpty).length;
      _translatePollTimer?.cancel();
      _translatePollTimer =
          Timer.periodic(const Duration(seconds: 8), (t) async {
        attempts++;
        if (attempts > 24) {
          unawaited(
            asrErrorReporter?.report(
                  kind: 'translate_poll_exhausted',
                  message: 'open translate poll stopped after 24 attempts',
                  stage: 'translate_poll',
                  cacheId: o.cacheId,
                ) ??
                Future<void>.value(),
          );
          asrEvidenceBus?.record(
            'translate_poll_exhausted',
            severity: 'error',
            cacheId: o.cacheId,
            stage: 'translate_poll',
            details: {'attempts': 24},
            ok: false,
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
          final prior = session;
          final refreshed = await _client.openPaper(
            cid,
            translate: true,
            translatePoll: true,
          );
          if (session?.cacheId != cid) return;
          final si = prior!.sentenceIndex;
          final fi = prior.figureIndex;
          refreshed.sentenceIndex = si;
          refreshed.figureIndex = fi;
          refreshed.clampIndices();
          refreshed.preserveClientStateFrom(prior);
          session = refreshed;
          unawaited(_prefetchFigureWindow());
          final koN = refreshed.sentences
              .where((s) => s.textKo.trim().isNotEmpty)
              .length;
          if (koN != lastKoN) {
            lastKoN = koN;
            asrEvidenceBus?.record(
              'translate_poll_ko',
              severity: 'boundary',
              cacheId: cid,
              stage: 'translate_poll',
              ok: true,
              details: {
                'ko_sentence_n': koN,
                'ko_missing_n': refreshed.translationMissingCount,
                'translate_pending': refreshed.translatePending,
                'attempt': attempts,
              },
            );
          }
          if (!refreshed.needsTranslationBackfill) {
            _stopTranslatePoll();
          } else if (refreshed.translationMissingCount > 0 &&
              !refreshed.translatePending) {
            _stopTranslatePoll();
            await _backfillLocalMissingKo(refreshed);
            return;
          }
          notifyListeners();
        } catch (e) {
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
            final msg = e.toString();
            asrEvidenceBus?.record(
              'client_api_fail',
              severity: 'error',
              cacheId: cid,
              stage: 'translate_poll',
              message: msg.length > 200 ? msg.substring(0, 200) : msg,
              ok: false,
            );
          }
          if (attempts >= 2) {
            _stopTranslatePoll();
            final cur = session;
            if (cur != null && cur.cacheId == cid) {
              await _backfillLocalMissingKo(cur);
            }
          }
        }
      });
    }));
  }

  /// design/194 — load disk session then KO backfill (no open reader required).
  Future<void> _backfillLocalMissingKoFromDisk(String cacheId) async {
    final cid = cacheId.trim();
    if (cid.isEmpty) return;
    if (!await _paperDisk.hasSession(cid)) return;
    final raw = await _paperDisk.loadSessionJson(cid);
    if (raw == null) return;
    final o = ReadingSession.fromOpenJson(raw, fallbackCacheId: cid);
    await _backfillLocalMissingKo(o, requireOpen: false);
  }

  /// Fill empty text_ko via /api/translate/batch and persist to PaperDiskStore.
  /// [requireOpen] false = handoff/library path (persist disk; sync open session if match).
  Future<void> _backfillLocalMissingKo(
    ReadingSession o, {
    bool requireOpen = true,
  }) async {
    if (requireOpen && session?.cacheId != o.cacheId) return;
    final wantTr = await _wantTranslate();
    if (!wantTr) return;
    final missingIdx = <int>[];
    final texts = <String>[];
    for (var i = 0; i < o.sentences.length; i++) {
      final s = o.sentences[i];
      if (s.hasText && s.textKo.trim().isEmpty) {
        missingIdx.add(i);
        texts.add(s.text);
      }
    }
    if (texts.isEmpty) return;
    translateBackfillBusy = true;
    notifyListeners();
    asrEvidenceBus?.record(
      'translate_local_backfill_start',
      severity: 'lifecycle',
      cacheId: o.cacheId,
      stage: 'translate_local',
      ok: true,
      details: {
        'missing_n': texts.length,
        'require_open': requireOpen ? 1 : 0,
        'trigger': requireOpen ? 'reader' : 'handoff',
      },
    );
    try {
      const piece = 64;
      final filled = List<String>.filled(texts.length, '');
      for (var off = 0; off < texts.length; off += piece) {
        if (requireOpen && session?.cacheId != o.cacheId) return;
        final end = (off + piece > texts.length) ? texts.length : off + piece;
        final chunk = texts.sublist(off, end);
        final kos = await _client.translateBatchEnToKo(chunk);
        for (var j = 0; j < chunk.length; j++) {
          filled[off + j] = j < kos.length ? kos[j].trim() : '';
        }
        uploadStage =
            '번역 보충 ${end.clamp(0, texts.length)}/${texts.length}';
        notifyListeners();
      }
      final working = (requireOpen ? session : null) ?? o;
      if (requireOpen) {
        final cur = session;
        if (cur == null || cur.cacheId != o.cacheId) return;
      } else if (working.cacheId != o.cacheId) {
        return;
      }
      final base = requireOpen ? session! : o;
      final next = <SentenceView>[];
      var applied = 0;
      for (var i = 0; i < base.sentences.length; i++) {
        final s = base.sentences[i];
        final mi = missingIdx.indexOf(i);
        if (mi >= 0 && filled[mi].isNotEmpty) {
          next.add(
            SentenceView(
              id: s.id,
              text: s.text,
              section: s.section,
              textKo: filled[mi],
              qualityFlags: s.qualityFlags,
            ),
          );
          applied += 1;
        } else {
          next.add(s);
        }
      }
      base.sentences
        ..clear()
        ..addAll(next);
      base.translatePending = false;
      await _paperDisk.shadowPersistReadingSession(base);
      final live = session;
      if (!requireOpen &&
          live != null &&
          live.cacheId == base.cacheId &&
          !identical(live, base)) {
        live.sentences
          ..clear()
          ..addAll(List<SentenceView>.from(base.sentences));
        live.translatePending = false;
      }
      asrEvidenceBus?.record(
        'translate_local_backfill_done',
        severity: 'lifecycle',
        cacheId: o.cacheId,
        stage: 'translate_local',
        ok: true,
        details: {
          'applied_n': applied,
          'missing_n': texts.length,
          'require_open': requireOpen ? 1 : 0,
        },
      );
    } catch (e) {
      final msg = e.toString();
      asrEvidenceBus?.record(
        'translate_local_backfill_fail',
        severity: 'error',
        cacheId: o.cacheId,
        stage: 'translate_local',
        message: msg.length > 200 ? msg.substring(0, 200) : msg,
        ok: false,
      );
      error = '번역 보충에 실패했습니다.  잠시 후 다시 열어 주세요.';
    } finally {
      translateBackfillBusy = false;
      if (uploadStage.startsWith('번역 보충')) {
        uploadStage = '';
      }
      notifyListeners();
    }
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
    final openHid = asrEvidenceBus?.recordHandoff(
          fromStage: 'client_open',
          toStage: 'cache_open',
          cacheId: entry.id,
          stage: 'open',
        ) ??
        '';
    _lastOpenHandoffId = openHid.isEmpty ? null : openHid;
    asrEvidenceBus?.record(
      'reader_open',
      severity: 'lifecycle',
      cacheId: entry.id,
      stage: 'begin',
      details: {
        if (openHid.isNotEmpty) 'handoff_id': openHid,
      },
    );
    // design/130 — hang if open never returns (infinite spinner class).
    asrErrorReporter?.hang.begin(
      opId,
      stage: 'library_open',
      stallAfter: HangWatchdog.shortStall,
      paperTitle: entry.title,
      cacheId: entry.id,
    );
    try {
      ReadingSession o;
      final side = _hydrateSessions[entry.id.trim()];
      // design/181 — reuse hydrate side-session to avoid open∩PNG contention.
      if (side != null &&
          side.isValid &&
          side.sentenceCount > 0 &&
          (_hydrateActive.contains(entry.id.trim()) ||
              side.figures.any((f) => f.imageSrc.trim().isNotEmpty))) {
        o = side;
        asrEvidenceBus?.record(
          'reader_open',
          severity: 'lifecycle',
          cacheId: entry.id,
          stage: 'reuse_hydrate_session',
          ok: true,
          details: {
            'figure_count': o.figureCount,
            'hydrate_active': _hydrateActive.contains(entry.id.trim()) ? 1 : 0,
          },
        );
      } else if (await _paperDisk.hasSession(entry.id)) {
        // design/185 — local SoT open whenever disk has session (post-wipe / bulk).
        final raw = await _paperDisk.loadSessionJson(entry.id);
        if (raw == null) {
          error = '로컬 보관본을 찾을 수 없습니다. 논문을 다시 열어 동기화해 주세요.';
          return null;
        }
        o = ReadingSession.fromOpenJson(
          raw,
          fallbackTitle: entry.title,
          fallbackCacheId: entry.id,
        );
        // Inject figure PNGs from PaperDiskStore into imageSrc stubs.
        for (var i = 0; i < o.figures.length; i++) {
          final f = o.figures[i];
          if (f.imageSrc.trim().isNotEmpty) continue;
          final bytes = await _paperDisk.readFigureBytes(o.cacheId, f.id);
          if (bytes == null || bytes.isEmpty) continue;
          o.figures[i].imageSrc = figureDataUrlFromBytes(bytes);
        }
        asrEvidenceBus?.record(
          'reader_open',
          severity: 'lifecycle',
          cacheId: entry.id,
          stage: 'local_paper_disk',
          ok: true,
          details: {
            'figure_count': o.figureCount,
            'ingest_status': entry.ingestStatus,
          },
        );
      } else {
        final wantTr = await _wantTranslate();
        o = await _client.openPaper(entry.id, translate: wantTr);
      }
      asrErrorReporter?.hang.progress(opId, stage: 'library_open_ok');
      // Fail-closed: never keep a previous session when this open failed upstream.
      if (o.sentenceCount < 1) {
        error = '보관본에 문장이 없습니다. 재분석하거나 PDF를 다시 올려 주세요.';
        asrEvidenceBus?.record(
          'reader_open',
          severity: 'error',
          cacheId: entry.id,
          stage: 'fail',
          ok: false,
          code: 'open_empty',
        );
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
        final lm = raw.layoutMode.trim();
        if (lm.isNotEmpty) readerLayoutMode = lm;
      }

      session = o;
      // design/185 Phase 1 — shadow-copy session + figure PNGs to PaperDiskStore.
      unawaited(_paperDisk.shadowPersistReadingSession(o));
      // design/171 — disk inject before RAM hydrate merge.
      await _injectFiguresFromDisk(o);
      // design/169n — reuse bytes already fetched on library hydrate.
      final hydrated = _hydrateSessions[o.cacheId];
      if (hydrated != null) {
        o.preserveClientStateFrom(hydrated);
      }
      _hydrateSessions[o.cacheId] = o;
      _maybeShowQualityBanner(o);
      _maybeStartTranslatePoll(o);
      unawaited(_syncBookmarksForSession(o));
      unawaited(_syncAnnotationsForSession(o));
      // design/129 — fill current±1 images after sentences are on screen.
      unawaited(_prefetchFigureWindow());
      // Keep hydrating remaining figures in background if not done.
      enqueueFigureHydrate(o.cacheId);
      // design/80 — per-user chunk backfill (opt-in); errors surface on reader.
      unawaited(ensureShadowingChunks(entry.id, trigger: 'reader_open'));
      asrEvidenceBus?.record(
        'reader_open',
        severity: 'lifecycle',
        cacheId: o.cacheId,
        stage: 'ok',
        ok: true,
        details: {
          'sentence_count': o.sentenceCount,
          'figure_count': o.figureCount,
          'translate_pending': o.translatePending,
          'ko_sentence_n':
              o.sentences.where((s) => s.textKo.trim().isNotEmpty).length,
          if (openHid.isNotEmpty) 'handoff_id': openHid,
        },
      );
      // design/169g phase 4 — open success → reader tab consumer
      if (openHid.isNotEmpty) {
        asrEvidenceBus?.recordHandoff(
          fromStage: 'cache_open',
          toStage: 'reader_tab',
          cacheId: o.cacheId,
          stage: 'open',
          extra: {'handoff_id': openHid},
        );
      }
      return session;
    } on AsrApiException catch (e) {
      // WHY: leave prior session untouched only if we never assigned; clear on fail.
      error = e.message;
      asrEvidenceBus?.record(
        'reader_open',
        severity: 'error',
        cacheId: entry.id,
        stage: 'fail',
        ok: false,
        httpStatus: e.statusCode,
        message: e.message.length > 200 ? e.message.substring(0, 200) : e.message,
      );
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
    } on TimeoutException catch (_) {
      error = '서버 응답이 느립니다. 잠시 후 다시 열어 주세요.';
      asrEvidenceBus?.record(
        'reader_open',
        severity: 'error',
        cacheId: entry.id,
        stage: 'fail',
        ok: false,
        code: 'timeout',
        message: 'timeout',
      );
      unawaited(
        asrErrorReporter?.report(
              kind: 'client_api_timeout',
              message: 'library_open timeout',
              stage: 'library_open',
              paperTitle: entry.title,
              cacheId: entry.id,
            ) ??
            Future.value(),
      );
      return null;
    } catch (e) {
      error = '논문을 열지 못했습니다. 잠시 후 다시 시도해 주세요.';
      asrEvidenceBus?.record(
        'reader_open',
        severity: 'error',
        cacheId: entry.id,
        stage: 'fail',
        ok: false,
        message: e.toString().length > 200
            ? e.toString().substring(0, 200)
            : e.toString(),
      );
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


  /// When a Fig/Table chip appears on the current sentence, sync bottom figure.
  /// Chip buttons remain for manual jumps (product backlog item 9).
  Future<bool> _maybeAutoFollowVisibleFigChip() async {
    final s = session;
    if (s == null || !s.isValid || s.figureCount < 1) return false;
    final cur = s.currentSentence;
    if (cur == null || !cur.hasText) return false;
    final hints = fig.hintsForSentence(
      text: cur.text,
      captions: s.figures.map((f) => f.caption).toList(),
      slotKeys: s.figures.map((f) => f.slotKey).toList(),
      supplementaryMerged: s.supplementaryMerged,
    );
    if (hints.isEmpty) return false;
    final want = hints.first.figureIndex;
    if (want < 0 || want >= s.figureCount || want == s.figureIndex) {
      return false;
    }
    final beforeSent = s.sentenceIndex;
    s.figureIndex = want;
    assert(s.sentenceIndex == beforeSent, 'auto-follow must not move sentence');
    unawaited(_prefetchFigureWindow());
    return true;
  }

  Future<void> advanceSentence(int delta) async {
    final s = session;
    if (s == null || !s.isValid) return;
    // design/182 — latched highlight paint must not change sentence mid-drag.
    if (_annotations?.blocksReaderNavigation == true) return;
    final beforeFig = s.figureIndex;
    final from = s.sentenceIndex;
    s.advanceSentence(delta);
    assert(s.figureIndex == beforeFig, 'figure index must stay put');
    final to = s.sentenceIndex;
    if (from != to) {
      onSentenceIndexChanged?.call(from, to);
    }
    final followed = await _maybeAutoFollowVisibleFigChip();
    if (s.sentenceIndex % 20 == 0) {
      asrEvidenceBus?.record(
        'reader_cursor',
        severity: 'sample',
        cacheId: s.cacheId,
        stage: 'sentence',
        details: {'si': s.sentenceIndex, 'fi': s.figureIndex},
      );
    }
    notifyListeners();
    await _syncCursor(sentence: true, figure: followed);
    // design/123 — durable prefs on every sentence move (product 5C).
    await persistOpenedProgress();
  }

  Future<void> advanceFigure(int delta) async {
    final s = session;
    if (s == null || !s.isValid) return;
    final beforeSent = s.sentenceIndex;
    s.advanceFigure(delta);
    assert(s.sentenceIndex == beforeSent, 'sentence index must stay put');
    if (s.figureIndex % 5 == 0) {
      asrEvidenceBus?.record(
        'reader_cursor',
        severity: 'sample',
        cacheId: s.cacheId,
        stage: 'figure',
        details: {'si': s.sentenceIndex, 'fi': s.figureIndex},
      );
    }
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
    // design/182 — latched highlight paint must not change sentence mid-drag.
    if (_annotations?.blocksReaderNavigation == true) return;
    final beforeFig = s.figureIndex;
    final from = s.sentenceIndex;
    s.sentenceIndex = index;
    assert(s.figureIndex == beforeFig, 'sentence jump must not move figure');
    onSentenceIndexChanged?.call(from, index);
    final followed = await _maybeAutoFollowVisibleFigChip();
    notifyListeners();
    await _syncCursor(sentence: true, figure: followed);
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
    // design/180 — hydrate owns bytes for this paper; skip competing prefetch.
    if (_hydrateActive.contains(s.cacheId.trim())) return;
    // design/171 — skip network when ±1 already on session (disk/hydrate).
    final lo = (s.figureIndex - 1).clamp(0, s.figureCount - 1);
    final hi = (s.figureIndex + 1).clamp(0, s.figureCount - 1);
    var needNet = false;
    for (var i = lo; i <= hi; i++) {
      if (s.figures[i].imageSrc.trim().isEmpty) {
        needNet = true;
        break;
      }
    }
    if (!needNet) return;
    try {
      final window = await _withFigureNetGate(
        () => _client.fetchFigureWindow(
          sessionId: s.sessionId,
          center: s.figureIndex,
          span: 1,
          cacheId: s.cacheId,
          evidenceSource: 'reader_prefetch',
        ),
      );
      final rows = window.figures;
      // EDGE: session object may be replaced (translate poll) while in flight.
      final current = session;
      if (current == null || current.cacheId != s.cacheId) return;
      current.mergeFigureWindow(rows);
      await _persistFiguresFromWindowRows(
        current.cacheId,
        rows,
        contentHash: current.contentHash,
      );
      final emptyN = rows
          .where((r) => '${r['image_src'] ?? ''}'.trim().isEmpty)
          .length;
      final resDetails = <String, dynamic>{
        'window_n': rows.length,
        'empty_n': emptyN,
        'center': s.figureIndex,
        'source': 'reader_prefetch',
      };
      if (window.serverEmptyReasons.isNotEmpty) {
        resDetails['server_empty_reasons'] = window.serverEmptyReasons;
      }
      asrEvidenceBus?.record(
        'figure_window_res',
        severity: emptyN == rows.length && rows.isNotEmpty ? 'error' : 'boundary',
        cacheId: s.cacheId,
        stage: 'prefetch',
        ok: emptyN < rows.length || rows.isEmpty,
        details: resDetails,
      );
      notifyListeners();
    } catch (e) {
      // design/168d G1.7 — fail-closed UI, but report (was silent).
      asrEvidenceBus?.record(
        'figure_window_res',
        severity: 'error',
        cacheId: s.cacheId,
        stage: 'prefetch_fail',
        ok: false,
        message: e.toString().length > 200
            ? e.toString().substring(0, 200)
            : e.toString(),
      );
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

  void _noteIngestStageProgress(String stage, {int? percent}) {
    _autoResumeGate.noteProgress(
      normalizeIngestStageKey(stage, percent: percent ?? uploadPercent),
    );
  }

  /// On TimeoutException / 504: maybe arm auto resume after finally.
  bool _armAutoResumeAfterTimeout({required String stageHint}) {
    final key = normalizeIngestStageKey(stageHint, percent: uploadPercent);
    final should = _autoResumeGate.noteTimeout(key);
    asrEvidenceBus?.record(
      'client_api_timeout',
      severity: should ? 'lifecycle' : 'error',
      route: 'ingest_auto_resume',
      stage: key.length > 40 ? key.substring(0, 40) : key,
      ok: should,
      details: {
        'auto_resume': should,
        'consecutive': _autoResumeGate.consecutiveTimeouts,
        'max': kIngestAutoResumeMax,
      },
    );
    return should;
  }

  void _schedulePendingAutoResume() {
    if (!_pendingAutoResume) return;
    _pendingAutoResume = false;
    unawaited(Future<void>(() async {
      await Future<void>.delayed(const Duration(milliseconds: 400));
      if (_uploadCancelRequested || uploading || reanalyzing) return;
      final draftOk = await _draftResumable();
      if (!draftOk) return;
      error = null;
      resumeOfferVisible = false;
      notifyListeners();
      await resumePendingIfAny();
    }));
  }

  /// design/158 — discard local upload draft (user opts out of resume).
  Future<void> discardResumeDraft() async {
    final draft = await _drafts.read();
    await _drafts.clear();
    await _cancelWorkmanager();
    resumeOfferVisible = false;
    _autoResumeGate.reset();
    _pendingAutoResume = false;
    error = null;
    if (draft != null) {
      await removeUploadQueueItem(draft.contentHash);
    }
    notifyListeners();
    unawaited(_pumpUploadQueue());
  }

  void clearOpened() {
    shadowingChunksError = null;
    shadowingChunksProgress = null;
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
    shadowingChunksProgress = null;
    shadowingChunksCacheId = null;
    shadowingChunksBusy = false;
    _softPurgeTimer?.cancel();
    _softPurgeTimer = null;
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
    // design/171 — clear RAM hydrate; keep disk for same-uid re-login.
    _hydrateSessions.clear();
    _figureHydrate.clear();
    _hydrateQueue.clear();
    _hydrateDismissed.clear();
    _clearPendingEnrichState();
    _figureDisk.bindUid(null);
    // design/185 — keep paper disk for same-uid re-login.
    _paperDisk.bindUid(null);
    _shadowDisk.bindUid(null);
    _diskUid = null;
    await _cancelWorkmanager();
    await _editStash.purgeAll();
    await _drafts.clear();
    await _reserve.clear();
    await _pickerRecent.clearBound();
    final oldGrant = pdfFolderGrant;
    final oldDl = pdfDownloadsGrant;
    await _pdfFolderGrant.clearBound();
    await _pdfDownloadsGrant.clearBound();
    await _pdfHashCache.clearBound();
    await _pdfAdvisoryCache.clearBound();
    _pdfAdvisoryPumpEpoch++;
    if (oldGrant != null) {
      unawaited(_safTree.releaseTree(oldGrant.treeUri));
    }
    if (oldDl != null &&
        (oldGrant == null || oldDl.treeUri != oldGrant.treeUri)) {
      unawaited(_safTree.releaseTree(oldDl.treeUri));
    }
    pdfFolderGrant = null;
    pdfFolderEntries = const [];
    pdfFolderTruncated = false;
    pdfFolderGrantStale = false;
    pdfDownloadsGrant = null;
    pdfDownloadsEntries = const [];
    pdfDownloadsTruncated = false;
    pdfDownloadsGrantStale = false;
    pdfImportBrowseMode = PdfImportBrowseMode.papers;
    await _softDelete.clearBound();
    uploadQueue = const [];
    pickerRecent = const [];
    libraryContentHashes = const {};
    pendingAutoOpenCacheId = null;
    _uploadQueueAutoOpened = false;
    _uploadPumpBusy = false;
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



  Future<void> _persistShadowingPlanIfOk(
    String cacheId,
    Map<String, dynamic> body,
  ) async {
    final plan = body['plan'];
    if (plan is! Map) return;
    if (plan['status']?.toString() != 'ok') return;
    final map = Map<String, dynamic>.from(plan);
    final ok = await _shadowDisk.writeChunkPlanJson(cacheId, map);
    asrEvidenceBus?.record(
      'shadowing_plan_local_save',
      cacheId: cacheId,
      severity: 'lifecycle',
      ok: ok,
      details: {
        'sentence_n': plan['sentences'] is Map
            ? (plan['sentences'] as Map).length
            : -1,
      },
    );
  }

  /// design/80 · design/113 — backfill/retry; pending slices auto-continue.
  /// design/169p — ensure_start/done + gate evidence.
  /// 0.3.176 — client TimeoutException on GET/build is *continue*, not hard error.
  Future<void> ensureShadowingChunks(
    String cacheId, {
    String trigger = 'unspecified',
  }) async {
    final id = cacheId.trim();
    if (id.isEmpty) return;
    final trig = trigger.trim().isEmpty ? 'unspecified' : trigger.trim();
    // Join in-flight ensure for same paper — do not reset progress / dual-build.
    if (_shadowingEnsureFuture != null && _shadowingEnsureCacheId == id) {
      asrEvidenceBus?.record(
        'shadowing_ensure_join',
        cacheId: id,
        severity: 'decision',
        ok: true,
        details: {
          'trigger': trig,
          'joined_cache_id': id,
          'busy': shadowingChunksBusy ? 1 : 0,
          'progress': shadowingChunksProgress ?? '',
        },
      );
      await _shadowingEnsureFuture;
      return;
    }
    if (_shadowingEnsureFuture != null) {
      final other = _shadowingEnsureCacheId ?? '';
      asrEvidenceBus?.record(
        'shadowing_ensure_wait_other',
        cacheId: id,
        severity: 'decision',
        ok: true,
        details: {
          'trigger': trig,
          'waiting_for': other,
          'other_progress': shadowingChunksProgress ?? '',
        },
      );
      try {
        await _shadowingEnsureFuture;
      } catch (_) {}
    }
    final run = _ensureShadowingChunksBody(id, trigger: trig);
    _shadowingEnsureFuture = run;
    _shadowingEnsureCacheId = id;
    try {
      await run;
    } finally {
      if (_shadowingEnsureCacheId == id) {
        _shadowingEnsureFuture = null;
        _shadowingEnsureCacheId = null;
      }
    }
  }

  /// Single-flight ensure body (design/80 · 113) + dense evidence (0.3.193).
  Future<void> _ensureShadowingChunksBody(
    String id, {
    required String trigger,
  }) async {
    shadowingChunksCacheId = id;
    final probe = await _shadowingWantProbe();
    if (!probe.want) {
      // WHY: preference/kill off → no banner success pretend.
      asrEvidenceBus?.record(
        'shadowing_gate',
        cacheId: id,
        severity: 'decision',
        ok: false,
        code: probe.gate,
        details: {
          'gate': probe.gate,
          'server_flag': probe.serverFlag,
          'pref': probe.pref,
        },
      );
      shadowingChunksError = null;
      shadowingChunksProgress = null;
      shadowingChunksBusy = false;
      notifyListeners();
      return;
    }
    shadowingChunksBusy = true;
    shadowingChunksError = null;
    shadowingChunksProgress = null;
    notifyListeners();
    final sw = Stopwatch()..start();
    final ensureId =
        'ens_${DateTime.now().millisecondsSinceEpoch.toRadixString(16)}';
    asrEvidenceBus?.record(
      'shadowing_ensure_start',
      cacheId: id,
      severity: 'lifecycle',
      details: {
        'trigger': trigger,
        'ensure_id': ensureId,
      },
    );
    var rounds = 0;
    var planStatus = '';
    var errorCode = '';
    var okOut = false;
    var timeoutContinues = 0;
    var lastProgDone = -1;
    var lastProgTotal = -1;
    var progressEmitN = 0;

    ({int? done, int? total}) _readProgress(Map<String, dynamic> body) {
      int? d;
      int? tot;
      final doneRaw = body['progress_done'];
      final totalRaw = body['progress_total'];
      d = doneRaw is int ? doneRaw : int.tryParse('$doneRaw');
      tot = totalRaw is int ? totalRaw : int.tryParse('$totalRaw');
      final plan = body['plan'];
      if (plan is Map) {
        final prog = plan['progress'];
        if (prog is Map) {
          final pd = prog['done'];
          final pt = prog['total'];
          d = pd is int ? pd : (int.tryParse('$pd') ?? d);
          tot = pt is int ? pt : (int.tryParse('$pt') ?? tot);
        }
      }
      return (done: d, total: tot);
    }

    void applyProgress(Map<String, dynamic> body, {String source = ''}) {
      final p = _readProgress(body);
      final d = p.done;
      final tot = p.total;
      if (d != null && tot != null && tot > 0) {
        shadowingChunksProgress = '$d/$tot';
        final changed = d != lastProgDone || tot != lastProgTotal;
        final filled = d >= tot;
        if (changed || filled) {
          lastProgDone = d;
          lastProgTotal = tot;
          progressEmitN += 1;
          asrEvidenceBus?.record(
            'shadowing_ensure_progress',
            cacheId: id,
            severity: 'sample',
            ok: filled,
            details: {
              'ensure_id': ensureId,
              'trigger': trigger,
              'source': source,
              'done': d,
              'total': tot,
              'filled': filled ? 1 : 0,
              'emit_n': progressEmitN,
              'round': rounds,
              'plan_status': planStatus,
            },
          );
        }
      }
    }

    try {
      var needBuild = true;
      final localPlan = await _shadowDisk.loadChunkPlanJson(id);
      if (localPlan != null && localPlan['status']?.toString() == 'ok') {
        asrEvidenceBus?.record(
          'shadowing_ensure_skip_ok',
          cacheId: id,
          severity: 'decision',
          ok: true,
          details: {
            'ensure_id': ensureId,
            'trigger': trigger,
            'source': 'local_disk',
          },
        );
        shadowingChunksError = null;
        shadowingChunksProgress = null;
        okOut = true;
        needBuild = false;
      }
      if (needBuild) {
      try {
        final got = await _client.fetchShadowingChunks(id);
        applyProgress(got, source: 'get');
        final plan = got['plan'];
        final status = plan is Map ? plan['status']?.toString() : null;
        planStatus = status ?? '';
        final prog = _readProgress(got);
        asrEvidenceBus?.record(
          'shadowing_ensure_get',
          cacheId: id,
          severity: 'lifecycle',
          ok: status == 'ok',
          details: {
            'ensure_id': ensureId,
            'trigger': trigger,
            'plan_status': planStatus,
            'done': prog.done ?? -1,
            'total': prog.total ?? -1,
            'sentence_n': plan is Map && plan['sentences'] is Map
                ? (plan['sentences'] as Map).length
                : -1,
          },
        );
        if (status == 'ok') {
          asrEvidenceBus?.record(
            'shadowing_ensure_skip_ok',
            cacheId: id,
            severity: 'decision',
            ok: true,
            details: {
              'ensure_id': ensureId,
              'trigger': trigger,
              'source': 'get',
              'done': prog.done ?? -1,
              'total': prog.total ?? -1,
            },
          );
          await _persistShadowingPlanIfOk(id, got);
          shadowingChunksError = null;
          shadowingChunksProgress = null;
          okOut = true;
          needBuild = false;
        }
      } on TimeoutException {
        // design/113 — GET stall (cold start / large plan) must not red-banner.
        timeoutContinues++;
        planStatus = planStatus.isEmpty ? 'pending' : planStatus;
        needBuild = true;
        asrEvidenceBus?.record(
          'shadowing_ensure_timeout_continue',
          cacheId: id,
          severity: 'boundary',
          ok: true,
          code: 'get_timeout',
          details: {
            'ensure_id': ensureId,
            'trigger': trigger,
            'timeout_continues': timeoutContinues,
            'phase': 'get',
          },
        );
        notifyListeners();
      }
      } // needBuild: skip cloud GET when local chunks.json already ok

      if (needBuild) {
        // design/113 — several budget slices until ok/error (cap avoids infinite).
        const maxSlices = 40;
        for (var i = 0; i < maxSlices; i++) {
          Map<String, dynamic> built;
          final sliceRound = i + 1;
          asrEvidenceBus?.record(
            'shadowing_ensure_slice_start',
            cacheId: id,
            severity: 'lifecycle',
            details: {
              'ensure_id': ensureId,
              'trigger': trigger,
              'round': sliceRound,
              'max_slices': maxSlices,
              'last_done': lastProgDone,
              'last_total': lastProgTotal,
              'phase': 'before_payload',
            },
          );
          try {
            final sentenceRows = await _shadowingSentencesPayload(id);
            asrEvidenceBus?.record(
              'shadowing_ensure_slice_start',
              cacheId: id,
              severity: 'sample',
              details: {
                'ensure_id': ensureId,
                'trigger': trigger,
                'round': sliceRound,
                'sentence_payload': sentenceRows?.length ?? 0,
                'phase': 'after_payload',
              },
            );
            built = await _client.buildShadowingChunks(
              id,
              practiceEnabled: true,
              sentences: sentenceRows,
              round: sliceRound,
              ensureId: ensureId,
              trigger: trigger,
            );
            rounds = sliceRound;
          } on TimeoutException {
            // Slice still running server-side; keep busy and resume.
            timeoutContinues++;
            planStatus = planStatus.isEmpty ? 'pending' : planStatus;
            asrEvidenceBus?.record(
              'shadowing_ensure_timeout_continue',
              cacheId: id,
              severity: 'boundary',
              ok: true,
              code: 'build_timeout',
              details: {
                'ensure_id': ensureId,
                'trigger': trigger,
                'round': sliceRound,
                'timeout_continues': timeoutContinues,
                'phase': 'build',
              },
            );
            notifyListeners();
            await Future<void>.delayed(Duration(seconds: 1 + (i % 3)));
            continue;
          } on AsrApiException catch (e) {
            // EDGE: legacy gateway 504 before budget fix — retry a few times.
            if (e.statusCode == 504 && i < 5) {
              await Future<void>.delayed(Duration(seconds: 2 + i));
              continue;
            }
            rethrow;
          }
          applyProgress(built, source: 'build');
          final p2 = built['plan'];
          final st2 = p2 is Map ? p2['status']?.toString() : null;
          planStatus = st2 ?? '';
          final sliceProg = _readProgress(built);
          asrEvidenceBus?.record(
            'shadowing_ensure_slice_done',
            cacheId: id,
            severity: 'lifecycle',
            ok: st2 == 'ok',
            details: {
              'ensure_id': ensureId,
              'trigger': trigger,
              'round': rounds,
              'plan_status': planStatus,
              'continue': built['continue'] == true ? 1 : 0,
              'done': sliceProg.done ?? -1,
              'total': sliceProg.total ?? -1,
              'filled': (sliceProg.done != null &&
                      sliceProg.total != null &&
                      sliceProg.done! >= sliceProg.total!)
                  ? 1
                  : 0,
            },
          );
          if (st2 == 'ok') {
            await _persistShadowingPlanIfOk(id, built);
            shadowingChunksError = null;
            shadowingChunksProgress = null;
            okOut = true;
            return;
          }
          if (st2 == 'pending' || built['continue'] == true) {
            // Honest in-progress — keep busy banner, next slice immediately.
            notifyListeners();
            continue;
          }
          if (st2 == 'error' || built['ok'] == false) {
            final msg = built['message']?.toString();
            errorCode =
                built['error']?.toString() ??
                (p2 is Map ? p2['error']?.toString() : null) ??
                'build_failed';
            shadowingChunksError =
                (msg != null && msg.isNotEmpty)
                    ? msg
                    : '연습 구간을 만들지 못했습니다. 다시 시도해 주세요.';
            return;
          }
          // Unknown shape — fail closed (no silent success).
          errorCode = 'unknown_shape';
          shadowingChunksError = '연습 구간을 만들지 못했습니다. 다시 시도해 주세요.';
          return;
        }
        errorCode = timeoutContinues > 0 ? 'timeout_cap' : 'cap_hit';
        shadowingChunksError =
            '연습 구간 준비가 아직 끝나지 않았습니다. 다시 시도해 주세요.';
      }
    } on AsrApiException catch (e) {
      errorCode = 'api_fail';
      shadowingChunksError = e.message;
    } catch (_) {
      errorCode = 'ensure_error';
      shadowingChunksError = '연습 구간 준비 중 오류가 났습니다. 다시 시도해 주세요.';
    } finally {
      asrEvidenceBus?.record(
        'shadowing_ensure_done',
        cacheId: id,
        severity: 'lifecycle',
        ok: okOut,
        code: errorCode,
        details: {
          'ensure_id': ensureId,
          'trigger': trigger,
          'plan_status': planStatus,
          'rounds': rounds,
          'elapsed_ms': sw.elapsedMilliseconds,
          'timeout_continues': timeoutContinues,
          'last_done': lastProgDone,
          'last_total': lastProgTotal,
          'progress_emit_n': progressEmitN,
          'filled': (lastProgDone >= 0 &&
                  lastProgTotal > 0 &&
                  lastProgDone >= lastProgTotal)
              ? 1
              : 0,
          if (errorCode.isNotEmpty) 'error_code': errorCode,
        },
      );
      shadowingChunksBusy = false;
      if (okOut) shadowingChunksProgress = null;
      notifyListeners();
    }
  }

  Future<void> retryShadowingChunks() async {
    final cache = shadowingChunksCacheId;
    if (cache == null || cache.isEmpty) return;
    await ensureShadowingChunks(cache, trigger: 'retry');
  }

  Future<bool> _wantShadowingPractice() async {
    final probe = await _shadowingWantProbe();
    return probe.want;
  }

  /// design/169p — classify kill vs pref for gate evidence (no text).
  Future<({bool want, String gate, bool serverFlag, bool pref})>
      _shadowingWantProbe() async {
    try {
      final st = await _client.fetchStatus();
      final serverFlag =
          st.mobileShadowingPractice || st.mobileShadowingChunks;
      if (!serverFlag) {
        return (want: false, gate: 'kill_off', serverFlag: false, pref: false);
      }
      final auth = await _client.fetchAuthStatus();
      final uid = auth.user?.uid;
      if (uid == null || uid.isEmpty) {
        return (want: false, gate: 'pref_off', serverFlag: true, pref: false);
      }
      final p = await SharedPreferences.getInstance();
      final pref =
          parseShadowingEnabledPref(p.getString(shadowingPrefsKey(uid)));
      if (!pref) {
        return (want: false, gate: 'pref_off', serverFlag: true, pref: false);
      }
      return (want: true, gate: '', serverFlag: true, pref: true);
    } catch (_) {
      return (want: false, gate: 'pref_off', serverFlag: false, pref: false);
    }
  }

  /// design/99 — Settings translate opt-in (default OFF).
  ///
  /// Prefer in-memory Settings switch ([_translateEnabled]) so a brief auth
  /// blip cannot send translate=0 on reanalyze while the toggle stays ON.
  Future<bool> _wantTranslate() async {
    final live = _translateEnabled;
    if (live != null) {
      try {
        return live();
      } catch (_) {
        // Fall through to prefs.
      }
    }
    // design/181 — during figure hydrate, avoid auth_status competing with PNG traffic.
    if (_hydrateActive.isNotEmpty) {
      return false;
    }
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
    asrEvidenceBus?.record(
      'ingest_cancel',
      severity: 'lifecycle',
      stage: 'begin',
      jobId: (_activeJobId ?? '').trim(),
      ok: true,
    );
    // WHY: pre-CD live has no cancel route — a bare 404 must not look like success wipe.
    try {
      final st = await _client.fetchStatus();
      if (!st.mobileIngestCancel) {
        error = '지금은 취소를 사용할 수 없습니다.';
        asrEvidenceBus?.record(
          'ingest_cancel',
          severity: 'error',
          stage: 'unavailable',
          ok: false,
          code: 'cancel_unavailable',
        );
        notifyListeners();
        return;
      }
    } catch (_) {
      // EDGE: status probe failed — refuse cancel rather than fake discard.
      error = '지금은 취소를 사용할 수 없습니다.';
      asrEvidenceBus?.record(
        'ingest_cancel',
        severity: 'error',
        stage: 'status_fail',
        ok: false,
      );
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
    // design/221 — cancel active only; pending reserved stay; pump continues.
    final activeHash = (_activeContentHash ?? '').trim();
    if (activeHash.isNotEmpty) {
      await removeUploadQueueItem(activeHash);
    }
    unawaited(_pumpUploadQueue());
  }

  /// design/221 — load prefs queue (+ migrate singleton draft into list for UI).
  Future<void> hydrateUploadQueue({bool pump = false}) async {
    var q = await _reserve.read();
    final draft = await _drafts.read();
    if (draft != null &&
        draft.purpose != 'reanalyze' &&
        !q.items.any((e) => e.contentHash == draft.contentHash)) {
      // WHY: reserve reader only allows ingest_reserve/; copy from draft tree.
      var reservePath = '';
      if (draft.localPath.contains('ingest_reserve')) {
        reservePath = draft.localPath;
      } else if (draft.localPath.isNotEmpty) {
        final raw = await _drafts.readLocalPdf(draft.localPath);
        if (raw != null && raw.isNotEmpty) {
          reservePath = await _reserve.saveLocalPdf(draft.contentHash, raw) ?? '';
        }
      }
      final migrated = UploadReserveItem(
        contentHash: draft.contentHash,
        filename: draft.filename,
        localPath: reservePath,
        bytesLen: draft.bytesLen,
        status: 'active',
        enqueuedAtMs: DateTime.now().millisecondsSinceEpoch,
      );
      q = UploadReserveQueue(items: [migrated, ...q.items]);
      await _reserve.write(q);
      asrEvidenceBus?.record(
        'upload_queue_enqueue',
        severity: 'lifecycle',
        stage: 'migrate_draft',
        details: {'n': 1, 'hash8': draft.contentHash.substring(0, 8)},
      );
    }
    uploadQueue = q.items;
    notifyListeners();
    if (pump) {
      unawaited(_pumpUploadQueue());
    }
  }


  /// design/226 — load grant + scan folder PDFs.
  Future<void> loadPdfFolderGrantAndScan({String trigger = 'load'}) async {
    pdfFolderGrantStale = false;
    final grant = await _pdfFolderGrant.read();
    pdfFolderGrant = grant;
    if (grant == null) {
      pdfFolderEntries = const [];
      pdfFolderTruncated = false;
      pdfFolderWritable = null;
      notifyListeners();
      return;
    }
    await _scanPdfFolder(grant.treeUri, trigger: trigger);
    await refreshPdfFolderWritable();
  }

  /// design/241 — proactive writable probe for READ-only banner.
  Future<void> refreshPdfFolderWritable() async {
    final grant = pdfFolderGrant;
    if (grant == null) {
      pdfFolderWritable = null;
      notifyListeners();
      return;
    }
    final probe = await _safTree.probeTreeWritable(grant.treeUri);
    pdfFolderWritable = probe.writable;
    asrEvidenceBus?.record(
      'pdf_tree_write_probe',
      severity: 'lifecycle',
      stage: 'write',
      details: {'ok': probe.writable, 'writable': probe.writable},
    );
    notifyListeners();
  }

  /// design/238 — debounced rescan of connected tree (resume / after pick).
  Future<void> rescanPdfFolderDebounced({
    String trigger = 'resume',
    int debounceMs = 1000,
  }) async {
    final grant = pdfFolderGrant;
    if (grant == null) return;
    final now = DateTime.now().millisecondsSinceEpoch;
    if (now - _pdfFolderRescanDebounceMs < debounceMs) return;
    _pdfFolderRescanDebounceMs = now;
    await _scanPdfFolder(grant.treeUri, trigger: trigger);
    unawaited(ensureVisiblePdfHashes());
    unawaited(ensureVisiblePdfAdvisories());
    _pollFindWatchAfterScan();
  }

  Future<bool> connectPdfFolder() async {
    final t0 = DateTime.now().millisecondsSinceEpoch;
    asrEvidenceBus?.record(
      'pdf_folder_grant_start',
      severity: 'lifecycle',
      stage: 'pick',
    );
    try {
      final picked = await _safTree.pickTree();
      final elapsed = DateTime.now().millisecondsSinceEpoch - t0;
      if (picked == null) {
        asrEvidenceBus?.record(
          'pdf_folder_grant_done',
          severity: 'lifecycle',
          stage: 'pick',
          details: {'ok': false, 'elapsed_ms': elapsed},
        );
        return false;
      }
      final prev = pdfFolderGrant;
      if (prev != null && prev.treeUri != picked.treeUri) {
        unawaited(_safTree.releaseTree(prev.treeUri));
      }
      final grant = PdfFolderGrant(
        treeUri: picked.treeUri,
        displayLabel: picked.displayLabel,
        grantedAtMs: DateTime.now().millisecondsSinceEpoch,
      );
      await _pdfFolderGrant.write(grant);
      pdfFolderGrant = grant;
      pdfFolderGrantStale = false;
      asrEvidenceBus?.record(
        'pdf_folder_grant_done',
        severity: 'lifecycle',
        stage: 'pick',
        details: {'ok': true, 'elapsed_ms': elapsed},
      );
      await _scanPdfFolder(grant.treeUri, trigger: 'connect');
      await refreshPdfFolderWritable();
      return true;
    } catch (_) {
      asrEvidenceBus?.record(
        'pdf_folder_grant_done',
        severity: 'error',
        stage: 'pick',
        details: {
          'ok': false,
          'elapsed_ms': DateTime.now().millisecondsSinceEpoch - t0,
        },
      );
      return false;
    }
  }


  /// design/248 — load Downloads tree grant + scan.
  Future<void> loadPdfDownloadsGrantAndScan({String trigger = 'load'}) async {
    pdfDownloadsGrantStale = false;
    final grant = await _pdfDownloadsGrant.read();
    pdfDownloadsGrant = grant;
    if (grant == null) {
      pdfDownloadsEntries = const [];
      pdfDownloadsTruncated = false;
      notifyListeners();
      return;
    }
    await _scanPdfFolder(
      grant.treeUri,
      trigger: trigger,
      target: PdfImportBrowseMode.downloads,
    );
  }

  Future<void> rescanPdfDownloadsDebounced({
    String trigger = 'resume',
    int debounceMs = 1000,
  }) async {
    final grant = pdfDownloadsGrant;
    if (grant == null) return;
    final now = DateTime.now().millisecondsSinceEpoch;
    if (now - _pdfDownloadsRescanDebounceMs < debounceMs) return;
    _pdfDownloadsRescanDebounceMs = now;
    await _scanPdfFolder(
      grant.treeUri,
      trigger: trigger,
      target: PdfImportBrowseMode.downloads,
    );
    if (pdfImportBrowseMode == PdfImportBrowseMode.downloads) {
      unawaited(ensureVisiblePdfHashes());
      unawaited(ensureVisiblePdfAdvisories());
    }
  }

  /// design/248 — connect Downloads via OPEN_DOCUMENT_TREE (hinted).
  Future<bool> connectPdfDownloadsFolder() async {
    final t0 = DateTime.now().millisecondsSinceEpoch;
    asrEvidenceBus?.record(
      'pdf_folder_grant_start',
      severity: 'lifecycle',
      stage: 'pick',
      details: {'browse': 'downloads'},
    );
    try {
      final picked = await _safTree.pickTree();
      final elapsed = DateTime.now().millisecondsSinceEpoch - t0;
      if (picked == null) {
        asrEvidenceBus?.record(
          'pdf_folder_grant_done',
          severity: 'lifecycle',
          stage: 'pick',
          details: {'ok': false, 'elapsed_ms': elapsed, 'browse': 'downloads'},
        );
        return false;
      }
      final prev = pdfDownloadsGrant;
      if (prev != null && prev.treeUri != picked.treeUri) {
        final papersUri = pdfFolderGrant?.treeUri;
        if (papersUri == null || prev.treeUri != papersUri) {
          unawaited(_safTree.releaseTree(prev.treeUri));
        }
      }
      final grant = PdfFolderGrant(
        treeUri: picked.treeUri,
        displayLabel: picked.displayLabel,
        grantedAtMs: DateTime.now().millisecondsSinceEpoch,
      );
      await _pdfDownloadsGrant.write(grant);
      pdfDownloadsGrant = grant;
      pdfDownloadsGrantStale = false;
      asrEvidenceBus?.record(
        'pdf_folder_grant_done',
        severity: 'lifecycle',
        stage: 'pick',
        details: {'ok': true, 'elapsed_ms': elapsed, 'browse': 'downloads'},
      );
      await _scanPdfFolder(
        grant.treeUri,
        trigger: 'connect',
        target: PdfImportBrowseMode.downloads,
      );
      return true;
    } catch (_) {
      asrEvidenceBus?.record(
        'pdf_folder_grant_done',
        severity: 'error',
        stage: 'pick',
        details: {
          'ok': false,
          'elapsed_ms': DateTime.now().millisecondsSinceEpoch - t0,
          'browse': 'downloads',
        },
      );
      return false;
    }
  }

  /// design/248 — switch to Downloads in-app browse; connect if needed.
  Future<bool> openDownloadsBrowse({bool connectIfMissing = true}) async {
    pdfImportBrowseMode = PdfImportBrowseMode.downloads;
    notifyListeners();
    if (pdfDownloadsGrant == null) {
      await loadPdfDownloadsGrantAndScan(trigger: 'open_downloads');
    } else if (pdfDownloadsEntries.isEmpty && !pdfDownloadsGrantStale) {
      await _scanPdfFolder(
        pdfDownloadsGrant!.treeUri,
        trigger: 'open_downloads',
        target: PdfImportBrowseMode.downloads,
      );
    }
    if (pdfDownloadsGrant == null && connectIfMissing) {
      final ok = await connectPdfDownloadsFolder();
      if (!ok) {
        notifyListeners();
        return false;
      }
    }
    if (pdfFindWatchArmed) {
      disarmFindWatch(reason: 'pick');
    }
    unawaited(ensureVisiblePdfHashes());
    unawaited(ensureVisiblePdfAdvisories());
    notifyListeners();
    return pdfDownloadsGrant != null;
  }


  List<ScannedPdfEntry> get pdfImportActiveEntries =>
      pdfImportBrowseMode == PdfImportBrowseMode.downloads
          ? pdfDownloadsEntries
          : pdfFolderEntries;

  bool get pdfImportActiveTruncated =>
      pdfImportBrowseMode == PdfImportBrowseMode.downloads
          ? pdfDownloadsTruncated
          : pdfFolderTruncated;

  PdfFolderGrant? get pdfImportActiveGrant =>
      pdfImportBrowseMode == PdfImportBrowseMode.downloads
          ? pdfDownloadsGrant
          : pdfFolderGrant;

  bool get pdfImportActiveGrantStale =>
      pdfImportBrowseMode == PdfImportBrowseMode.downloads
          ? pdfDownloadsGrantStale
          : pdfFolderGrantStale;

  void setPdfImportBrowseMode(PdfImportBrowseMode mode) {
    if (pdfImportBrowseMode == mode) return;
    pdfImportBrowseMode = mode;
    notifyListeners();
  }

  Future<void> _scanPdfFolder(
    String treeUri, {
    String trigger = 'scan',
    PdfImportBrowseMode target = PdfImportBrowseMode.papers,
  }) async {
    _pdfAdvisoryPumpEpoch++;
    final t0 = DateTime.now().millisecondsSinceEpoch;
    final prev = target == PdfImportBrowseMode.downloads
        ? pdfDownloadsEntries
        : pdfFolderEntries;
    final prevUris = {for (final e in prev) e.docUri};
    try {
      final listed = await _safTree.listPdfs(
        treeUri,
        maxItems: kPdfFolderScanMaxItems,
      );
      final next = <ScannedPdfEntry>[];
      for (final it in listed.items) {
        final cached = await _pdfHashCache.lookup(
          docUri: it.docUri,
          sizeBytes: it.sizeBytes,
          lastModifiedMs: it.lastModifiedMs,
        );
        final adv = await _pdfAdvisoryCache.lookup(
          docUri: it.docUri,
          sizeBytes: it.sizeBytes,
          lastModifiedMs: it.lastModifiedMs,
        );
        next.add(
          ScannedPdfEntry(
            docUri: it.docUri,
            displayName: it.displayName,
            sizeBytes: it.sizeBytes,
            lastModifiedMs: it.lastModifiedMs,
            contentHash: cached ?? '',
            hashState:
                cached == null ? PdfHashState.unknown : PdfHashState.ready,
            advisoryTitle: adv?.advisoryTitle ?? '',
            advisoryRole: adv?.advisoryRole ?? '',
            advisoryReason: adv?.advisoryReason ?? '',
            advisoryState: adv == null
                ? PdfAdvisoryState.unknown
                : PdfAdvisoryState.ready,
            advisoryDoi: adv?.advisoryDoi ?? '',
            pairingKey: (adv?.pairingKey ?? '').isNotEmpty
                ? adv!.pairingKey
                : (adv != null && adv.advisoryTitle.trim().isNotEmpty
                    ? normalizePairingKey(adv.advisoryTitle)
                    : ''),
          ),
        );
      }
      if (target == PdfImportBrowseMode.downloads) {
        pdfDownloadsEntries = next;
        pdfDownloadsTruncated = listed.truncated;
        pdfDownloadsGrantStale = false;
      } else {
        pdfFolderEntries = next;
        pdfFolderTruncated = listed.truncated;
        pdfFolderGrantStale = false;
      }
      final nHashReady =
          next.where((e) => e.hashState == PdfHashState.ready).length;
      final nAdvReady =
          next.where((e) => e.advisoryState == PdfAdvisoryState.ready).length;
      final nAdvUnknown =
          next.where((e) => e.advisoryState == PdfAdvisoryState.unknown).length;
      final nNew = next.where((e) => !prevUris.contains(e.docUri)).length;
      asrEvidenceBus?.record(
        'pdf_folder_scan_done',
        severity: 'lifecycle',
        stage: 'scan',
        details: {
          'n': next.length,
          'truncated': listed.truncated,
          'n_hash_ready': nHashReady,
          'n_adv_ready': nAdvReady,
          'n_adv_unknown': nAdvUnknown,
          'elapsed_ms': DateTime.now().millisecondsSinceEpoch - t0,
          'browse':
              target == PdfImportBrowseMode.downloads ? 'downloads' : 'papers',
        },
      );
      asrEvidenceBus?.record(
        'pdf_folder_rescan_done',
        severity: 'lifecycle',
        stage: 'scan',
        details: {
          'n': next.length,
          'n_new': nNew,
          'elapsed_ms': DateTime.now().millisecondsSinceEpoch - t0,
          'trigger': _evidenceSnakeToken(trigger, fallback: 'scan'),
        },
      );
      notifyListeners();
    } on PlatformException catch (e) {
      if (e.code == 'stale') {
        if (target == PdfImportBrowseMode.downloads) {
          pdfDownloadsGrantStale = true;
          pdfDownloadsEntries = const [];
        } else {
          pdfFolderGrantStale = true;
          pdfFolderEntries = const [];
        }
        asrEvidenceBus?.record(
          'pdf_folder_grant_stale',
          severity: 'warn',
          stage: 'scan',
          details: {'ok': false},
        );
        notifyListeners();
        return;
      }
      if (target == PdfImportBrowseMode.downloads) {
        pdfDownloadsEntries = const [];
      } else {
        pdfFolderEntries = const [];
      }
      notifyListeners();
    } catch (_) {
      if (target == PdfImportBrowseMode.downloads) {
        pdfDownloadsEntries = const [];
      } else {
        pdfFolderEntries = const [];
      }
      notifyListeners();
    }
  }

  /// design/226 · 230 — lazy hash unknown rows (concurrency 2).
  Future<void> ensureVisiblePdfHashes({int limit = 40}) async {
    final active = pdfImportActiveEntries;
    final unknownAll = active
        .where((e) => e.hashState == PdfHashState.unknown)
        .toList();
    if (_pdfHashPumpBusy) {
      asrEvidenceBus?.record(
        'pdf_hash_pump_start',
        severity: 'lifecycle',
        stage: 'hash',
        details: {
          'skipped_busy': true,
          'n_unknown': unknownAll.length,
          'limit': limit,
        },
      );
      return;
    }
    _pdfHashPumpBusy = true;
    final tPump = DateTime.now().millisecondsSinceEpoch;
    var nOk = 0;
    var nFail = 0;
    try {
      final beyond = unknownAll.length > limit ? unknownAll.length - limit : 0;
      final pending = unknownAll.take(limit).toList();
      if (pending.isEmpty) {
        asrEvidenceBus?.record(
          'pdf_hash_pump_done',
          severity: 'lifecycle',
          stage: 'hash',
          details: {
            'n': 0,
            'limit': limit,
            'n_beyond_limit': beyond,
            'n_ok': 0,
            'n_fail': 0,
            'n_unknown_left': 0,
            'elapsed_ms': DateTime.now().millisecondsSinceEpoch - tPump,
          },
        );
        return;
      }
      asrEvidenceBus?.record(
        'pdf_hash_pump_start',
        severity: 'lifecycle',
        stage: 'hash',
        details: {
          'n': pending.length,
          'limit': limit,
          'n_unknown_total': unknownAll.length,
          'n_beyond_limit': beyond,
        },
      );
      for (final e in pending) {
        e.hashState = PdfHashState.computing;
      }
      notifyListeners();
      Future<void> one(ScannedPdfEntry e) async {
        final t0 = DateTime.now().millisecondsSinceEpoch;
        try {
          final hex = await _safTree.sha256OfUri(e.docUri);
          if (hex == null) {
            e.hashState = PdfHashState.failed;
            nFail += 1;
            asrEvidenceBus?.record(
              'pdf_hash_cache_fail',
              severity: 'warn',
              stage: 'hash',
              details: {'code': 'null'},
            );
            return;
          }
          e.contentHash = hex;
          e.hashState = PdfHashState.ready;
          await _pdfHashCache.put(
            docUri: e.docUri,
            sizeBytes: e.sizeBytes,
            lastModifiedMs: e.lastModifiedMs,
            contentHash: hex,
          );
          nOk += 1;
          final h8 = 'h_${hex.substring(0, 8)}';
          asrEvidenceBus?.record(
            'pdf_hash_cache_miss',
            severity: 'debug',
            stage: 'hash',
            details: {
              'elapsed_ms': DateTime.now().millisecondsSinceEpoch - t0,
              'h8': h8,
            },
          );
        } catch (_) {
          e.hashState = PdfHashState.failed;
          nFail += 1;
          asrEvidenceBus?.record(
            'pdf_hash_cache_fail',
            severity: 'warn',
            stage: 'hash',
            details: {'code': 'exc'},
          );
        }
      }

      for (var i = 0; i < pending.length; i += 2) {
        final batch = pending.skip(i).take(2).map(one);
        await Future.wait(batch);
        notifyListeners();
      }
      final nUnknownLeft = pdfImportActiveEntries
          .where((e) => e.hashState == PdfHashState.unknown)
          .length;
      asrEvidenceBus?.record(
        'pdf_hash_pump_done',
        severity: 'lifecycle',
        stage: 'hash',
        details: {
          'n': pending.length,
          'limit': limit,
          'n_beyond_limit': beyond,
          'n_ok': nOk,
          'n_fail': nFail,
          'n_unknown_left': nUnknownLeft,
          'elapsed_ms': DateTime.now().millisecondsSinceEpoch - tPump,
        },
      );
    } finally {
      _pdfHashPumpBusy = false;
    }
  }

  void cancelPdfAdvisoryPump() {
    _pdfAdvisoryPumpEpoch++;
  }

  static String _evidenceSnakeToken(String raw, {String fallback = 'other'}) {
    var s = raw.trim().toLowerCase();
    s = s.replaceAll(RegExp(r'[^a-z0-9_]+'), '_');
    s = s.replaceAll(RegExp(r'_+'), '_');
    if (s.startsWith('_')) s = s.substring(1);
    if (s.isEmpty || !RegExp(r'^[a-z][a-z0-9_]{0,63}$').hasMatch(s)) {
      return fallback;
    }
    return s;
  }

  /// design/228 · 230 — lazy advisory title/role (concurrency 2, first [limit]).
  Future<void> ensureVisiblePdfAdvisories({int limit = 40}) async {
    final unknownAll = pdfImportActiveEntries
        .where((e) => e.advisoryState == PdfAdvisoryState.unknown)
        .toList();
    if (_pdfAdvisoryPumpBusy) {
      asrEvidenceBus?.record(
        'pdf_advisory_pump_skip',
        severity: 'lifecycle',
        stage: 'advisory',
        details: {
          'reason': 'busy',
          'n_unknown': unknownAll.length,
          'n_entries': pdfImportActiveEntries.length,
          'limit': limit,
        },
      );
      return;
    }
    _pdfAdvisoryPumpBusy = true;
    final epoch = _pdfAdvisoryPumpEpoch;
    final tPump = DateTime.now().millisecondsSinceEpoch;
    var nOk = 0;
    var nFail = 0;
    var nHit = 0;
    var nMiss = 0;
    var nCancelled = 0;
    final reasonHist = <String, int>{};
    final codeHist = <String, int>{};
    final titleSrcHist = <String, int>{};

    void bump(Map<String, int> m, String key) {
      m[key] = (m[key] ?? 0) + 1;
    }

    try {
      final nReadyPre = pdfImportActiveEntries
          .where((e) => e.advisoryState == PdfAdvisoryState.ready)
          .length;
      final nFailedPre = pdfImportActiveEntries
          .where((e) => e.advisoryState == PdfAdvisoryState.failed)
          .length;
      final beyond = unknownAll.length > limit ? unknownAll.length - limit : 0;
      final pending = unknownAll.take(limit).toList();
      if (pending.isEmpty) {
        asrEvidenceBus?.record(
          'pdf_advisory_pump_skip',
          severity: 'lifecycle',
          stage: 'advisory',
          details: {
            'reason': 'empty_pending',
            'n_unknown': 0,
            'n_entries': pdfImportActiveEntries.length,
            'n_ready_pre': nReadyPre,
            'n_failed_pre': nFailedPre,
            'limit': limit,
          },
        );
        return;
      }
      asrEvidenceBus?.record(
        'pdf_advisory_pump_start',
        severity: 'lifecycle',
        stage: 'advisory',
        details: {
          'n': pending.length,
          'limit': limit,
          'n_unknown_total': unknownAll.length,
          'n_beyond_limit': beyond,
          'n_ready_pre': nReadyPre,
          'n_failed_pre': nFailedPre,
        },
      );
      for (final e in pending) {
        e.advisoryState = PdfAdvisoryState.computing;
      }
      notifyListeners();

      Future<void> one(ScannedPdfEntry e) async {
        if (epoch != _pdfAdvisoryPumpEpoch) return;
        final t0 = DateTime.now().millisecondsSinceEpoch;
        try {
          final cached = await _pdfAdvisoryCache.lookup(
            docUri: e.docUri,
            sizeBytes: e.sizeBytes,
            lastModifiedMs: e.lastModifiedMs,
          );
          if (epoch != _pdfAdvisoryPumpEpoch) return;
          if (cached != null) {
            e.advisoryTitle = cached.advisoryTitle;
            e.advisoryRole = cached.advisoryRole;
            e.advisoryReason = cached.advisoryReason;
            e.advisoryDoi = cached.advisoryDoi;
            e.pairingKey = cached.pairingKey.isNotEmpty
                ? cached.pairingKey
                : await _pairingKeyForTitle(cached.advisoryTitle);
            e.advisoryState = PdfAdvisoryState.ready;
            nOk += 1;
            nHit += 1;
            bump(reasonHist, _evidenceSnakeToken(cached.advisoryReason));
            final ts = cached.titleSource.isEmpty
                ? 'unknown'
                : _evidenceSnakeToken(cached.titleSource, fallback: 'unknown');
            bump(titleSrcHist, ts);
            asrEvidenceBus?.record(
              'pdf_advisory_cache_hit',
              severity: 'debug',
              stage: 'advisory',
              details: {
                'n': 1,
                'role': cached.advisoryRole,
                'reason': _evidenceSnakeToken(cached.advisoryReason),
                'title_source': ts,
              },
            );
            _emitDoiEvidence(
              doi: cached.advisoryDoi,
              source: cached.doiSource,
              role: cached.advisoryRole,
            );
            return;
          }
          // design/249 — docx: filename advisory only (no PdfBox).
          final isDocx =
              e.displayName.toLowerCase().endsWith('.docx');
          if (isDocx) {
            final title = _docxAdvisoryTitle(e.displayName);
            final role = filenameLooksLikeSi(e.displayName)
                ? 'supplementary'
                : 'main';
            final reason =
                role == 'supplementary' ? 'filename_si' : 'filename_main';
            e.advisoryTitle = title;
            e.advisoryRole = role;
            e.advisoryReason = reason;
            e.advisoryDoi = '';
            e.pairingKey = await _pairingKeyForTitle(title);
            e.advisoryState = PdfAdvisoryState.ready;
            await _pdfAdvisoryCache.put(
              docUri: e.docUri,
              sizeBytes: e.sizeBytes,
              lastModifiedMs: e.lastModifiedMs,
              advisoryTitle: title,
              advisoryRole: role,
              advisoryReason: reason,
              extractOk: true,
              titleSource: 'filename',
              advisoryDoi: '',
              doiSource: '',
              pairingKey: e.pairingKey,
            );
            nOk += 1;
            nMiss += 1;
            bump(reasonHist, _evidenceSnakeToken(reason));
            bump(titleSrcHist, 'filename');
            asrEvidenceBus?.record(
              'pdf_advisory_cache_miss',
              severity: 'debug',
              stage: 'advisory',
              details: {
                'elapsed_ms': DateTime.now().millisecondsSinceEpoch - t0,
                'role': role,
                'reason': _evidenceSnakeToken(reason),
                'extract_ok': true,
                'head_len': 0,
                'kind': 'docx',
              },
            );
            _emitDoiEvidence(doi: '', source: '', role: role);
            return;
          }
          final head = await _safTree.extractPdfHead(e.docUri);
          if (epoch != _pdfAdvisoryPumpEpoch) return;
          if (!head.ok) {
            e.advisoryState = PdfAdvisoryState.failed;
            nFail += 1;
            final code = head.code.isEmpty ? 'extract' : head.code;
            bump(codeHist, _evidenceSnakeToken(code));
            asrEvidenceBus?.record(
              'pdf_advisory_cache_fail',
              severity: 'warn',
              stage: 'advisory',
              details: {'code': _evidenceSnakeToken(code)},
            );
            return;
          }
          final det = detectDocRoleDetailed(
            head.headText,
            filename: e.displayName,
          );
          final guessed = guessAdvisoryTitle(
            infoTitle: head.infoTitle,
            headText: head.headText,
            displayName: e.displayName,
          );
          var doi = extractDoiFromText(head.headText) ?? '';
          var doiSource = doi.isNotEmpty ? 'head' : '';
          if (doi.isEmpty) {
            doi = extractDoiFromText(head.infoTitle) ?? '';
            if (doi.isNotEmpty) doiSource = 'info';
          }
          e.advisoryTitle = guessed.title;
          e.advisoryRole = det.role;
          e.advisoryReason = det.reason;
          e.advisoryDoi = doi;
          e.pairingKey = await _pairingKeyForTitle(guessed.title);
          e.advisoryState = PdfAdvisoryState.ready;
          await _pdfAdvisoryCache.put(
            docUri: e.docUri,
            sizeBytes: e.sizeBytes,
            lastModifiedMs: e.lastModifiedMs,
            advisoryTitle: guessed.title,
            advisoryRole: det.role,
            advisoryReason: det.reason,
            extractOk: true,
            titleSource: guessed.source,
            advisoryDoi: doi,
            doiSource: doiSource,
            pairingKey: e.pairingKey,
          );
          nOk += 1;
          nMiss += 1;
          bump(reasonHist, _evidenceSnakeToken(det.reason));
          bump(titleSrcHist, _evidenceSnakeToken(guessed.source));
          asrEvidenceBus?.record(
            'pdf_advisory_cache_miss',
            severity: 'debug',
            stage: 'advisory',
            details: {
              'elapsed_ms': DateTime.now().millisecondsSinceEpoch - t0,
              'role': det.role,
              'reason': _evidenceSnakeToken(det.reason),
              'extract_ok': true,
              'head_len': head.headText.length,
              'page_count': head.pageCount,
              'truncated': head.truncated,
              'title_source': _evidenceSnakeToken(guessed.source),
            },
          );
          _emitDoiEvidence(doi: doi, source: doiSource, role: det.role);
        } catch (err) {
          if (epoch != _pdfAdvisoryPumpEpoch) return;
          e.advisoryState = PdfAdvisoryState.failed;
          nFail += 1;
          bump(codeHist, 'exc');
          asrEvidenceBus?.record(
            'pdf_advisory_cache_fail',
            severity: 'warn',
            stage: 'advisory',
            details: {
              'code': 'exc',
              'exc_type': _evidenceSnakeToken(
                err.runtimeType.toString(),
                fallback: 'unknown',
              ),
            },
          );
        }
      }

      for (var i = 0; i < pending.length; i += 2) {
        if (epoch != _pdfAdvisoryPumpEpoch) {
          nCancelled = pending.length - i;
          asrEvidenceBus?.record(
            'pdf_advisory_cancelled',
            severity: 'lifecycle',
            stage: 'advisory',
            details: {'n_abandoned': nCancelled},
          );
          break;
        }
        final batch = pending.skip(i).take(2).map(one);
        await Future.wait(batch);
        notifyListeners();
      }
      final nUnknownLeft = pdfImportActiveEntries
          .where((e) => e.advisoryState == PdfAdvisoryState.unknown)
          .length;
      final nFailedLeft = pdfImportActiveEntries
          .where((e) => e.advisoryState == PdfAdvisoryState.failed)
          .length;
      final nReadyLeft = pdfImportActiveEntries
          .where((e) => e.advisoryState == PdfAdvisoryState.ready)
          .length;
      final doneDetails = <String, Object?>{
        'n_ok': nOk,
        'n_fail': nFail,
        'n_hit': nHit,
        'n_miss': nMiss,
        'n_cancelled': nCancelled,
        'n_unknown_left': nUnknownLeft,
        'n_failed_left': nFailedLeft,
        'n_ready_left': nReadyLeft,
        'n_beyond_limit': beyond,
        'elapsed_ms': DateTime.now().millisecondsSinceEpoch - tPump,
      };
      for (final e in reasonHist.entries) {
        doneDetails['n_reason_${e.key}'] = e.value;
      }
      for (final e in codeHist.entries) {
        doneDetails['n_code_${e.key}'] = e.value;
      }
      for (final e in titleSrcHist.entries) {
        doneDetails['n_title_src_${e.key}'] = e.value;
      }
      asrEvidenceBus?.record(
        'pdf_advisory_pump_done',
        severity: 'lifecycle',
        stage: 'advisory',
        details: doneDetails,
      );
    } finally {
      _pdfAdvisoryPumpBusy = false;
    }
  }

  void _emitDoiEvidence({
    required String doi,
    required String source,
    required String role,
  }) {
    final roleTok = role.trim().toLowerCase() == 'supplementary' ? 'si' : 'main';
    if (doi.trim().isNotEmpty) {
      asrEvidenceBus?.record(
        'pdf_advisory_doi_hit',
        severity: 'debug',
        stage: 'advisory',
        details: {
          'ok': true,
          'source': _evidenceSnakeToken(
            source.isEmpty ? 'unknown' : source,
            fallback: 'unknown',
          ),
          'role': roleTok,
        },
      );
    } else {
      asrEvidenceBus?.record(
        'pdf_advisory_doi_miss',
        severity: 'debug',
        stage: 'advisory',
        details: {'ok': false, 'role': roleTok},
      );
    }
  }

  /// design/237 · 242 — after DOI find CTA opens browser.
  /// design/239 — prefer Android NFKC then Dart normalizePairingKey.
  Future<String> _pairingKeyForTitle(String title) async {
    final raw = title.trim();
    if (raw.isEmpty) return '';
    try {
      final nfkc = await _safTree.normalizeNfkc(raw);
      if (nfkc != null && nfkc.isNotEmpty) {
        return normalizePairingKey(nfkc);
      }
    } catch (_) {}
    return normalizePairingKey(raw);
  }

  void armFindWatch({int windowMs = 120000}) {
    var baseline = 0;
    for (final e in pdfFolderEntries) {
      if (e.lastModifiedMs > baseline) baseline = e.lastModifiedMs;
    }
    final now = DateTime.now().millisecondsSinceEpoch;
    pdfFindWatchArmed = true;
    pdfFindWatchUntilMs = now + windowMs;
    pdfFindWatchBaselineMs = baseline;
    pdfFindWatchHitDocUri = null;
    _pdfFindWatchHandled = false;
    _pdfFindWatchIgnoreUris.clear();
    asrEvidenceBus?.record(
      'pdf_find_watch_arm',
      severity: 'lifecycle',
      stage: 'find',
      details: {'ok': true, 'window_ms': windowMs},
    );
    notifyListeners();
  }

  void noteFindWatchIgnore(String docUri) {
    final u = docUri.trim();
    if (u.isNotEmpty) _pdfFindWatchIgnoreUris.add(u);
  }

  void _bumpFindWatchBaselineFromEntries() {
    var baseline = pdfFindWatchBaselineMs;
    for (final e in pdfFolderEntries) {
      if (e.lastModifiedMs > baseline) baseline = e.lastModifiedMs;
    }
    pdfFindWatchBaselineMs = baseline;
  }

  void disarmFindWatch({String reason = 'cancel'}) {
    if (!pdfFindWatchArmed && pdfFindWatchHitDocUri == null) return;
    final wasArmed = pdfFindWatchArmed;
    pdfFindWatchArmed = false;
    pdfFindWatchUntilMs = 0;
    pdfFindWatchBaselineMs = 0;
    pdfFindWatchHitDocUri = null;
    _pdfFindWatchHandled = false;
    if (wasArmed) {
      asrEvidenceBus?.record(
        'pdf_find_watch_disarm',
        severity: 'lifecycle',
        stage: 'find',
        details: {'reason': _evidenceSnakeToken(reason, fallback: 'cancel')},
      );
    }
    notifyListeners();
  }

  void confirmFindWatchHit({required bool accepted}) {
    asrEvidenceBus?.record(
      'pdf_find_watch_confirm',
      severity: 'lifecycle',
      stage: 'find',
      details: {'accepted': accepted},
    );
    // Hit already in connected tree — caller selects URI; never delete.
    pdfFindWatchArmed = false;
    _pdfFindWatchHandled = true;
    if (!accepted) {
      pdfFindWatchHitDocUri = null;
    }
    // Keep hit URI briefly for highlight when accepted; clear on next arm/disarm.
    notifyListeners();
  }

  void _pollFindWatchAfterScan() {
    if (!pdfFindWatchArmed || _pdfFindWatchHandled) return;
    final now = DateTime.now().millisecondsSinceEpoch;
    if (now > pdfFindWatchUntilMs) {
      asrEvidenceBus?.record(
        'pdf_find_watch_timeout',
        severity: 'lifecycle',
        stage: 'find',
        details: {'ok': false},
      );
      disarmFindWatch(reason: 'timeout');
      return;
    }
    ScannedPdfEntry? newest;
    for (final e in pdfFolderEntries) {
      if (_pdfFindWatchIgnoreUris.contains(e.docUri)) continue;
      if (e.lastModifiedMs <= pdfFindWatchBaselineMs) continue;
      if (newest == null || e.lastModifiedMs > newest.lastModifiedMs) {
        newest = e;
      }
    }
    if (newest == null) return;
    pdfFindWatchHitDocUri = newest.docUri;
    _pdfFindWatchHandled = true;
    asrEvidenceBus?.record(
      'pdf_find_watch_hit',
      severity: 'lifecycle',
      stage: 'find',
      details: {'ok': true},
    );
    notifyListeners();
  }

  /// design/249 — display-name stem for docx advisory title.
  String _docxAdvisoryTitle(String displayName) {
    var base = displayName.trim();
    if (base.isEmpty) return 'document';
    final slash = base.replaceAll('\\', '/').lastIndexOf('/');
    if (slash >= 0) base = base.substring(slash + 1);
    final lower = base.toLowerCase();
    if (lower.endsWith('.docx')) {
      base = base.substring(0, base.length - 5);
    } else if (lower.endsWith('.pdf')) {
      base = base.substring(0, base.length - 4);
    }
    base = base.trim();
    return base.isEmpty ? displayName.trim() : base;
  }

  /// design/237 — evidence for find CTA open/fail (never DOI plaintext).
  void recordFindOpen({required String role, required bool ok, String code = ''}) {
    final roleTok = role.trim().toLowerCase() == 'supplementary' ? 'si' : 'main';
    if (ok) {
      asrEvidenceBus?.record(
        'pdf_import_find_open',
        severity: 'lifecycle',
        stage: 'find',
        details: {'ok': true, 'role': roleTok},
      );
    } else {
      asrEvidenceBus?.record(
        'pdf_import_find_fail',
        severity: 'warn',
        stage: 'find',
        details: {
          'ok': false,
          'role': roleTok,
          'code': _evidenceSnakeToken(code.isEmpty ? 'launch' : code),
        },
      );
    }
  }

  /// design/239 — evidence when set rows are built for UI.
  void recordImportSetBuilt({
    required int nSets,
    required int nSingles,
    required int nGap,
  }) {
    asrEvidenceBus?.record(
      'pdf_import_set_built',
      severity: 'lifecycle',
      stage: 'import',
      details: {
        'n_sets': nSets,
        'n_singles': nSingles,
        'n_gap': nGap,
      },
    );
  }

  /// design/226 — read selected folder URIs then enqueue via 221.
  Future<({int added, int skipped, String? message})> enqueueFolderPdfs(
    List<String> docUris,
  ) async {
    final batch = <({String name, Uint8List bytes})>[];
    var skipped = 0;
    String? message;
    final byUri = {
      for (final e in pdfFolderEntries) e.docUri: e,
      for (final e in pdfDownloadsEntries) e.docUri: e,
    };
    for (final uri in docUris) {
      final e = byUri[uri];
      if (e == null) {
        skipped += 1;
        continue;
      }
      try {
        final bytes = await _safTree.readPdfBytes(uri);
        if (bytes == null || bytes.isEmpty) {
          skipped += 1;
          message = '파일을 읽지 못했습니다.';
          continue;
        }
        batch.add((name: e.displayName, bytes: bytes));
      } on PlatformException catch (ex) {
        skipped += 1;
        if (ex.code == 'too_large') {
          message = '파일이 너무 큽니다 (최대 50MB).';
        } else if (ex.code == 'stale') {
          pdfFolderGrantStale = true;
          message = '폴더 접근이 만료되었습니다. 다시 연결해 주세요.';
        } else {
          message = '파일을 읽지 못했습니다.';
        }
      } catch (_) {
        skipped += 1;
        message = '파일을 읽지 못했습니다.';
      }
    }
    if (batch.isEmpty) {
      return (added: 0, skipped: skipped, message: message);
    }
    final outcome = await enqueuePickedPdfs(batch);
    return (
      added: outcome.added,
      skipped: outcome.skipped + skipped,
      message: outcome.message ?? message,
    );
  }

  /// design/239 — atomic set enqueue: need ≥2 free slots; abort if either read fails.
  Future<({int added, int skipped, String? message})> enqueueFolderPdfSet(
    List<String> docUris,
  ) async {
    final uris = docUris.where((u) => u.trim().isNotEmpty).toList();
    if (uris.length < 2) {
      return enqueueFolderPdfs(uris);
    }
    final q = await _reserve.read();
    final room = kUploadReserveMaxItems - q.length;
    if (room < 2) {
      asrEvidenceBus?.record(
        'pdf_import_set_enqueue',
        severity: 'warn',
        stage: 'import',
        details: {'ok': false, 'n': 0, 'skipped': 1},
      );
      return (
        added: 0,
        skipped: 1,
        message: '세트로 추가하려면 대기열 자리가 2칸 필요합니다',
      );
    }
    final byUri = {
      for (final e in pdfFolderEntries) e.docUri: e,
      for (final e in pdfDownloadsEntries) e.docUri: e,
    };
    final batch = <({String name, Uint8List bytes})>[];
    for (final uri in uris.take(2)) {
      final e = byUri[uri];
      if (e == null) {
        asrEvidenceBus?.record(
          'pdf_import_set_enqueue',
          severity: 'warn',
          stage: 'import',
          details: {'ok': false, 'n': 0, 'skipped': 1},
        );
        return (added: 0, skipped: 1, message: '파일을 읽지 못했습니다.');
      }
      try {
        final bytes = await _safTree.readPdfBytes(uri);
        if (bytes == null || bytes.isEmpty) {
          asrEvidenceBus?.record(
            'pdf_import_set_enqueue',
            severity: 'warn',
            stage: 'import',
            details: {'ok': false, 'n': 0, 'skipped': 1},
          );
          return (added: 0, skipped: 1, message: '파일을 읽지 못했습니다.');
        }
        batch.add((name: e.displayName, bytes: bytes));
      } on PlatformException catch (ex) {
        final msg = ex.code == 'too_large'
            ? '파일이 너무 큽니다 (최대 50MB).'
            : (ex.code == 'stale'
                ? '폴더 접근이 만료되었습니다. 다시 연결해 주세요.'
                : '파일을 읽지 못했습니다.');
        if (ex.code == 'stale') pdfFolderGrantStale = true;
        asrEvidenceBus?.record(
          'pdf_import_set_enqueue',
          severity: 'warn',
          stage: 'import',
          details: {'ok': false, 'n': 0, 'skipped': 1},
        );
        return (added: 0, skipped: 1, message: msg);
      } catch (_) {
        asrEvidenceBus?.record(
          'pdf_import_set_enqueue',
          severity: 'warn',
          stage: 'import',
          details: {'ok': false, 'n': 0, 'skipped': 1},
        );
        return (added: 0, skipped: 1, message: '파일을 읽지 못했습니다.');
      }
    }
    final outcome = await enqueuePickedPdfs(batch);
    asrEvidenceBus?.record(
      'pdf_import_set_enqueue',
      severity: 'lifecycle',
      stage: 'import',
      details: {
        'ok': outcome.added >= 2,
        'n': outcome.added,
        'skipped': outcome.skipped,
      },
    );
    return outcome;
  }

  /// design/248 - import selected Downloads URIs into papers tree or enqueue.
  Future<({int copied, int enqueued, String? message, String mode})>
      importSelectedFromDownloads(List<String> docUris) async {
    final t0 = DateTime.now().millisecondsSinceEpoch;
    final uris = [for (final u in docUris) if (u.trim().isNotEmpty) u.trim()];
    asrEvidenceBus?.record(
      'pdf_import_pick_start',
      severity: 'lifecycle',
      stage: 'pick',
      details: {'ok': true, 'browse': 'downloads'},
    );
    if (uris.isEmpty) {
      asrEvidenceBus?.record(
        'pdf_import_pick_done',
        severity: 'lifecycle',
        stage: 'pick',
        details: {
          'ok': false,
          'n': 0,
          'elapsed_ms': DateTime.now().millisecondsSinceEpoch - t0,
          'mode': 'cancel',
        },
      );
      return (copied: 0, enqueued: 0, message: null, mode: 'cancel');
    }
    if (pdfFindWatchArmed) {
      disarmFindWatch(reason: 'pick');
    }
    final byUri = {for (final e in pdfDownloadsEntries) e.docUri: e};
    final picked = <({String docUri, String displayName})>[];
    for (final uri in uris) {
      final e = byUri[uri];
      if (e == null) continue;
      picked.add((docUri: e.docUri, displayName: e.displayName));
    }
    if (picked.isEmpty) {
      return (
        copied: 0,
        enqueued: 0,
        message: 'selected_missing',
        mode: 'cancel',
      );
    }
    final grant = pdfFolderGrant;
    var mode = 'enqueue';
    var copied = 0;
    var enqueued = 0;
    String? message;
    final failedPick = <({String docUri, String displayName})>[];
    if (grant != null) {
      final probe = await _safTree.probeTreeWritable(grant.treeUri);
      pdfFolderWritable = probe.writable;
      asrEvidenceBus?.record(
        'pdf_tree_write_probe',
        severity: 'lifecycle',
        stage: 'write',
        details: {'ok': probe.writable, 'writable': probe.writable},
      );
      if (probe.writable) {
        mode = 'copy';
        for (final it in picked) {
          final tc0 = DateTime.now().millisecondsSinceEpoch;
          asrEvidenceBus?.record(
            'pdf_tree_copy_start',
            severity: 'lifecycle',
            stage: 'write',
            details: {'ok': true},
          );
          try {
            final created = await _safTree.copyUriIntoTree(
              srcDocUri: it.docUri,
              treeUri: grant.treeUri,
              displayName: it.displayName,
            );
            if (created != null) {
              copied += 1;
              noteFindWatchIgnore(created.docUri);
              asrEvidenceBus?.record(
                'pdf_tree_copy_done',
                severity: 'lifecycle',
                stage: 'write',
                details: {
                  'ok': true,
                  'elapsed_ms': DateTime.now().millisecondsSinceEpoch - tc0,
                },
              );
            } else {
              failedPick.add(it);
              asrEvidenceBus?.record(
                'pdf_tree_copy_fail',
                severity: 'warn',
                stage: 'write',
                details: {'code': 'null'},
              );
            }
          } on PlatformException catch (ex) {
            failedPick.add(it);
            asrEvidenceBus?.record(
              'pdf_tree_copy_fail',
              severity: 'warn',
              stage: 'write',
              details: {'code': _evidenceSnakeToken(ex.code)},
            );
            message = ex.code == 'too_large' ? 'too_large' : 'copy_fail';
          } catch (_) {
            failedPick.add(it);
            asrEvidenceBus?.record(
              'pdf_tree_copy_fail',
              severity: 'warn',
              stage: 'write',
              details: {'code': 'exc'},
            );
            message = 'copy_fail';
          }
        }
        if (copied > 0) {
          pdfImportBrowseMode = PdfImportBrowseMode.papers;
          await _scanPdfFolder(grant.treeUri, trigger: 'after_copy');
          _bumpFindWatchBaselineFromEntries();
          unawaited(ensureVisiblePdfHashes());
          unawaited(ensureVisiblePdfAdvisories());
        }
        if (copied > 0 && failedPick.isNotEmpty) {
          mode = 'copy_partial';
          final batch = <({String name, Uint8List bytes})>[];
          for (final it in failedPick) {
            try {
              final bytes = await _safTree.readPdfBytes(it.docUri);
              if (bytes == null || bytes.isEmpty) continue;
              batch.add((name: it.displayName, bytes: bytes));
            } on PlatformException catch (ex) {
              if (ex.code == 'too_large') message = 'too_large';
            } catch (_) {}
          }
          if (batch.isNotEmpty) {
            final outcome = await enqueuePickedPdfs(batch);
            enqueued = outcome.added;
          }
          message = 'copy_partial';
        }
      }
    }
    if (copied == 0) {
      mode = 'enqueue';
      final batch = <({String name, Uint8List bytes})>[];
      for (final it in picked) {
        try {
          final bytes = await _safTree.readPdfBytes(it.docUri);
          if (bytes == null || bytes.isEmpty) continue;
          batch.add((name: it.displayName, bytes: bytes));
        } on PlatformException catch (ex) {
          if (ex.code == 'too_large') message = 'too_large';
        } catch (_) {}
      }
      if (batch.isNotEmpty) {
        final outcome = await enqueuePickedPdfs(batch);
        enqueued = outcome.added;
        message ??= outcome.message ??
            (grant == null ? 'enqueue_no_folder' : 'enqueue_nw');
      } else if (message == null) {
        message = 'read_failed';
      }
    }
    final uiMessage = _pdfImportUserMessage(
      message,
      copied: copied,
      failed: failedPick.length,
      enqueued: enqueued,
    );
    asrEvidenceBus?.record(
      'pdf_import_pick_done',
      severity: 'lifecycle',
      stage: 'pick',
      details: {
        'ok': copied > 0 || enqueued > 0,
        'n': copied + enqueued,
        'elapsed_ms': DateTime.now().millisecondsSinceEpoch - t0,
        'mode': mode,
        'browse': 'downloads',
      },
    );
    return (
      copied: copied,
      enqueued: enqueued,
      message: uiMessage,
      mode: mode,
    );
  }

  String? _pdfImportUserMessage(
    String? code, {
    required int copied,
    required int failed,
    required int enqueued,
  }) {
    if (code == null) return null;
    switch (code) {
      case 'selected_missing':
        return '선택한 파일을 찾지 못했습니다.';
      case 'too_large':
        return '파일이 너무 큽니다 (최대 50MB).';
      case 'copy_fail':
        return '폴더로 복사하지 못했습니다.';
      case 'enqueue_no_folder':
        return '폴더 미연결 — 대기열에만 추가했습니다.';
      case 'enqueue_nw':
        return '폴더에 복사할 수 없어 대기열에만 추가했습니다.';
      case 'read_failed':
        return '파일을 읽지 못했습니다.';
      case 'copy_partial':
        return '폴더에 $copied건 복사 · 실패 $failed건 중 대기열 $enqueued건';
      default:
        return code;
    }
  }

  /// design/223 — sheet open breadcrumb.
  void notePickerSheetOpened() {
    asrEvidenceBus?.record(
      'picker_sheet_open',
      severity: 'lifecycle',
      stage: 'sheet',
      details: {
        'recent_n': pickerRecent.length,
        'queue_n': uploadQueue.length,
        'lib_hash_n': libraryContentHashes.length,
      },
    );
  }

  Future<void> _reloadPickerRecent() async {
    final list = await _pickerRecent.read();
    pickerRecent = list.items;
    notifyListeners();
  }

  Future<void> _rebuildLibraryHashSet() async {
    final out = <String>{};
    for (final e in papers) {
      final h = e.contentHash.trim().toLowerCase();
      if (h.length == 64 && RegExp(r'^[a-f0-9]{64}$').hasMatch(h)) {
        // EDGE: failed rows still have hash — only skip explicit error status.
        if (e.ingestStatus.trim().toLowerCase() == 'error') continue;
        out.add(h);
      }
    }
    try {
      for (final e in await _paperDisk.listIndex()) {
        final h = e.contentHash.trim().toLowerCase();
        if (h.length == 64 && RegExp(r'^[a-f0-9]{64}$').hasMatch(h)) {
          out.add(h);
        }
      }
    } catch (_) {}
    libraryContentHashes = Set<String>.unmodifiable(out);
  }

  /// design/221 — enqueue one or more PDFs; serial pump starts if idle.
  Future<({int added, int skipped, String? message})> enqueuePickedPdfs(
    List<({String name, Uint8List bytes})> files,
  ) async {
    if (files.isEmpty) {
      return (added: 0, skipped: 0, message: null);
    }
    if (uploadQueue.isEmpty && !uploading) {
      _uploadQueueAutoOpened = false;
    }
    var q = await _reserve.read();
    var added = 0;
    var skipped = 0;
    String? message;
    final now = DateTime.now().millisecondsSinceEpoch;
    for (final f in files) {
      final name = f.name.trim();
      final bytes = f.bytes;
      if (name.isEmpty || bytes.isEmpty) {
        skipped += 1;
        continue;
      }
      if (q.length >= kUploadReserveMaxItems) {
        skipped += 1;
        message = '대기 목록이 가득 찼습니다 (최대 $kUploadReserveMaxItems건).';
        break;
      }
      final hash = sha256Hex(bytes);
      if (q.items.any((e) => e.contentHash == hash)) {
        skipped += 1;
        continue;
      }
      final path = await _reserve.saveLocalPdf(hash, bytes, filename: name);
      if (path == null || path.isEmpty) {
        skipped += 1;
        message = '파일을 저장하지 못했습니다.';
        continue;
      }
      final item = UploadReserveItem(
        contentHash: hash,
        filename: name,
        localPath: path,
        bytesLen: bytes.length,
        status: 'reserved',
        enqueuedAtMs: now + added,
      );
      q = UploadReserveQueue(items: [...q.items, item]);
      added += 1;
      await _pickerRecent.remember(
        contentHash: hash,
        displayName: name,
        source: 'saf',
      );
      asrEvidenceBus?.record(
        'upload_queue_enqueue',
        severity: 'lifecycle',
        stage: 'pick',
        details: {
          'n': 1,
          'hash8': hash.substring(0, 8),
          'bytes': bytes.length,
          'queue_len': q.length,
        },
      );
    }
    await _reserve.write(q);
    uploadQueue = q.items;
    if (added > 0) {
      await _reloadPickerRecent();
      asrEvidenceBus?.record(
        'picker_recent_save',
        severity: 'lifecycle',
        stage: 'enqueue',
        details: {'n': added},
      );
    }
    notifyListeners();
    unawaited(_pumpUploadQueue());
    return (added: added, skipped: skipped, message: message);
  }

  /// design/221 — remove a reserved (or orphan) item; never clears active singleton draft.
  Future<void> removeUploadQueueItem(String contentHash) async {
    final hash = contentHash.trim().toLowerCase();
    if (hash.length != 64) return;
    final q = await _reserve.read();
    UploadReserveItem? removed;
    final next = <UploadReserveItem>[];
    for (final it in q.items) {
      if (it.contentHash == hash) {
        removed = it;
        continue;
      }
      next.add(it);
    }
    if (removed == null) {
      uploadQueue = q.items;
      return;
    }
    await _reserve.deleteLocalPdf(removed.localPath);
    await _reserve.write(UploadReserveQueue(items: next));
    uploadQueue = next;
    asrEvidenceBus?.record(
      'upload_queue_remove',
      severity: 'lifecycle',
      stage: removed.isActive ? 'active_or_done' : 'reserved',
      details: {'hash8': hash.substring(0, 8)},
    );
    notifyListeners();
  }

  Future<void> _markQueueItemActive(String contentHash) async {
    final hash = contentHash.trim().toLowerCase();
    final q = await _reserve.read();
    final next = q.items
        .map(
          (e) => e.contentHash == hash
              ? e.copyWith(status: 'active')
              : (e.isActive ? e.copyWith(status: 'reserved') : e),
        )
        .toList();
    await _reserve.write(UploadReserveQueue(items: next));
    uploadQueue = next;
    notifyListeners();
  }

  Future<void> _pumpUploadQueue() async {
    if (_uploadPumpBusy) return;
    if (uploading || reanalyzing) return;
    _uploadPumpBusy = true;
    try {
      while (true) {
        if (uploading || reanalyzing) break;
        final draft = await _drafts.read();
        if (draft != null && draft.isReanalyze) {
          asrEvidenceBus?.record(
            'upload_queue_blocked',
            severity: 'lifecycle',
            stage: 'reanalyze_draft',
            ok: true,
          );
          break;
        }
        if (draft != null &&
            (draft.canReattach || draft.canResumeChunks)) {
          asrEvidenceBus?.record(
            'upload_queue_blocked',
            severity: 'lifecycle',
            stage: 'resumable_draft',
            details: {'hash8': draft.contentHash.substring(0, 8)},
            ok: true,
          );
          break;
        }

        final q = await _reserve.read();
        uploadQueue = q.items;
        final head = q.items.isEmpty
            ? null
            : q.items.firstWhere(
                (e) => e.isReserved || e.isActive,
                orElse: () => q.items.first,
              );
        if (head == null || q.isEmpty) break;

        final bytes = await _reserve.readLocalPdf(head.localPath);
        if (bytes == null || bytes.isEmpty) {
          final d = await _drafts.read();
          if (d != null &&
              d.contentHash == head.contentHash &&
              (d.canReattach || d.canResumeChunks)) {
            // EDGE: migrated active without reserve bytes — resume UI owns it.
            break;
          }
          await removeUploadQueueItem(head.contentHash);
          continue;
        }

        await _markQueueItemActive(head.contentHash);
        asrEvidenceBus?.record(
          'upload_queue_pump_start',
          severity: 'lifecycle',
          stage: 'head',
          details: {
            'hash8': head.contentHash.substring(0, 8),
            'queue_len': q.length,
          },
        );

        final result = await uploadPdf(
          filename: head.filename,
          bytes: Uint8List.fromList(bytes),
          knownHash: head.contentHash,
        );

        final still = await _drafts.read();
        if (result != null) {
          await removeUploadQueueItem(head.contentHash);
          asrEvidenceBus?.record(
            'upload_queue_pump_done',
            severity: 'lifecycle',
            stage: 'ok',
            cacheId: result.cacheId,
            ok: true,
            details: {'hash8': head.contentHash.substring(0, 8)},
          );
          if (!_uploadQueueAutoOpened && result.cacheId.trim().isNotEmpty) {
            pendingAutoOpenCacheId = result.cacheId.trim();
            _uploadQueueAutoOpened = true;
            notifyListeners();
          }
          continue;
        }

        if (still != null &&
            still.contentHash == head.contentHash &&
            (still.canReattach || still.canResumeChunks)) {
          asrEvidenceBus?.record(
            'upload_queue_pump_done',
            severity: 'lifecycle',
            stage: 'keep_resume',
            ok: false,
            details: {'hash8': head.contentHash.substring(0, 8)},
          );
          break;
        }

        await removeUploadQueueItem(head.contentHash);
        asrEvidenceBus?.record(
          'upload_queue_pump_done',
          severity: 'lifecycle',
          stage: 'fail_or_cancel',
          ok: false,
          details: {'hash8': head.contentHash.substring(0, 8)},
        );
      }
    } finally {
      _uploadPumpBusy = false;
      final q = await _reserve.read();
      uploadQueue = q.items;
      notifyListeners();
      if (q.items.any((e) => e.isReserved) && !uploading && !reanalyzing) {
        final draft = await _drafts.read();
        final blocked = draft != null &&
            (draft.isReanalyze ||
                draft.canReattach ||
                draft.canResumeChunks);
        if (!blocked) {
          unawaited(_pumpUploadQueue());
        }
      }
    }
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
    _pendingAutoResume = false;
    _autoResumeGate.reset();
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
        asrEvidenceBus?.record(
          'ingest_upload_start',
          severity: 'lifecycle',
          stage: 'begin',
          details: {
            'bytes': bytes.length,
            'chunked': true,
            'want_translate_pref': wantTr,
          },
        );
        asrEvidenceBus?.recordHandoff(
          fromStage: 'client_upload',
          toStage: 'ingest_queued',
          stage: 'upload',
          inN: bytes.length,
        );
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
        asrEvidenceBus?.recordHandoff(
          fromStage: 'ingest_queued',
          toStage: 'ingest_started',
          jobId: started.jobId,
          stage: 'upload',
          inN: bytes.length,
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
          _noteIngestStageProgress(uploadStage, percent: uploadPercent);
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
      _autoResumeGate.reset();
      // design/221 — drop finished head so a later pump cannot re-ingest.
      await removeUploadQueueItem(hash);
      await _runPaperHandoff(result.cacheId, title: result.title);
      final seen = await _confirmCacheInLibrary(
        result.cacheId,
        jobId: result.jobId,
        stage: 'after_upload',
      );
      if (!seen) {
        error = '업로드는 끝났지만 목록에 아직 없습니다. 새로고침해 주세요.';
        await _notify.showFailed(message: error!);
        notifyListeners();
        return null;
      }
      await _notify.showCompleted(cacheId: result.cacheId);
      enqueueFigureHydrate(result.cacheId);
      enqueueHarmonizeResidualPoll(
        result.cacheId,
        pendingHint: result.harmonizePending,
        totalHint: result.harmonizeTotal,
        doneHint: result.harmonizeDone,
        failedHint: result.harmonizeFailed,
        attemptHint: result.harmonizeAttemptN > 0 ? result.harmonizeAttemptN : 1,
      );
      return result;
    } on UploadCancelledException {
      // design/132 — honest cancel; design/134 hang keeps failure message.
      await _drafts.clear();
      await _cancelWorkmanager();
      await _notify.stop();
      _autoResumeGate.reset();
      _pendingAutoResume = false;
      if (!_ingestHangTripped) {
        error = null;
      }
      await refresh();
      return null;
    } on TimeoutException catch (e) {
      final stage = uploadStage.trim();
      error = stage.isNotEmpty
          ? '서버 응답이 느립니다. ($stage)'
          : '서버 응답이 느립니다. 「이어서 분석하기」를 눌러 주세요.';
      _pendingAutoResume = _armAutoResumeAfterTimeout(stageHint: stage);
      if (!_pendingAutoResume) {
        resumeOfferVisible = await _draftResumable();
      }
      asrEvidenceBus?.record(
        'client_api_timeout',
        severity: 'error',
        route: 'ingest_poll',
        stage: stage.isEmpty ? 'upload' : (stage.length > 40 ? stage.substring(0, 40) : stage),
        message: e.toString().length > 200 ? e.toString().substring(0, 200) : e.toString(),
        ok: false,
      );
      await _notify.showFailed(message: error!);
      await _refreshLibraryAfterIngestFail();
      return null;
    } on AsrApiException catch (e) {
      // design/109: terminal job (422) or lost/conflict — do not reattach forever.
      if (e.statusCode == 409 ||
          e.statusCode == 404 ||
          e.statusCode == 422) {
        await _drafts.clear();
        await _cancelWorkmanager();
        resumeOfferVisible = false;
        _autoResumeGate.reset();
        _pendingAutoResume = false;
      } else if (e.statusCode == 504 || _ingestHangTripped) {
        final stage = uploadStage.trim();
        _pendingAutoResume = _armAutoResumeAfterTimeout(stageHint: stage);
        if (!_pendingAutoResume) {
          resumeOfferVisible = await _draftResumable();
        }
      }
      // design/105 — surface last stage on timeout so failure is actionable.
      final stage = uploadStage.trim();
      if (e.statusCode == 504 && stage.isNotEmpty) {
        error = '${e.message} ($stage)';
      } else {
        error = e.message;
      }
      await _notify.showFailed(message: error!);
      // design/179 — GCS may still hold paper after API false worker_lost.
      await _refreshLibraryAfterIngestFail();
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
      if (_pendingAutoResume) {
        _schedulePendingAutoResume();
      } else {
        unawaited(_refreshResumeOffer());
      }
      // design/221 — resume/direct uploadPdf path; pump is no-op while already pumping.
      if (!_uploadPumpBusy) {
        unawaited(_pumpUploadQueue());
      }
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
    _pendingAutoResume = false;
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
          _noteIngestStageProgress(uploadStage, percent: uploadPercent);
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
      _autoResumeGate.reset();
      await removeUploadQueueItem(draft.contentHash);
      await _runPaperHandoff(result.cacheId, title: result.title);
      final seen = await _confirmCacheInLibrary(
        result.cacheId,
        jobId: result.jobId,
        stage: 'after_upload',
      );
      if (!seen) {
        error = '업로드는 끝났지만 목록에 아직 없습니다. 새로고침해 주세요.';
        await _notify.showFailed(message: error!);
        notifyListeners();
        return null;
      }
      await _notify.showCompleted(cacheId: result.cacheId);
      enqueueFigureHydrate(result.cacheId);
      enqueueHarmonizeResidualPoll(
        result.cacheId,
        pendingHint: result.harmonizePending,
        totalHint: result.harmonizeTotal,
        doneHint: result.harmonizeDone,
        failedHint: result.harmonizeFailed,
        attemptHint: result.harmonizeAttemptN > 0 ? result.harmonizeAttemptN : 1,
      );
      if (draft.isReanalyze && draft.cacheId.isNotEmpty) {
        final targetId =
            result.cacheId.isNotEmpty ? result.cacheId : draft.cacheId;
        final openEntry = paperEntryForCacheId(targetId);
        if (openEntry != null &&
            (session?.cacheId == draft.cacheId ||
                session?.cacheId == result.cacheId)) {
          await open(openEntry);
        }
      }
      return result;
    } on UploadCancelledException {
      await _drafts.clear();
      await _cancelWorkmanager();
      await _notify.stop();
      _autoResumeGate.reset();
      _pendingAutoResume = false;
      if (!_ingestHangTripped) {
        error = null;
      }
      await refresh();
      return null;
    } on TimeoutException catch (e) {
      final stage = uploadStage.trim();
      error = stage.isNotEmpty
          ? '서버 응답이 느립니다. ($stage)'
          : '서버 응답이 느립니다. 「이어서 분석하기」를 눌러 주세요.';
      _pendingAutoResume = _armAutoResumeAfterTimeout(stageHint: stage);
      if (!_pendingAutoResume) {
        resumeOfferVisible = await _draftResumable();
      }
      asrEvidenceBus?.record(
        'client_api_timeout',
        severity: 'error',
        route: 'ingest_poll_resume',
        stage: stage.isEmpty ? 'resume' : (stage.length > 40 ? stage.substring(0, 40) : stage),
        message: e.toString().length > 200 ? e.toString().substring(0, 200) : e.toString(),
        ok: false,
      );
      await _notify.showFailed(message: error!);
      await _refreshLibraryAfterIngestFail();
      return null;
    } on AsrApiException catch (e) {
      // design/109: same terminal cleanup as uploadPdf.
      if (e.statusCode == 409 ||
          e.statusCode == 404 ||
          e.statusCode == 422) {
        await _drafts.clear();
        await _cancelWorkmanager();
        resumeOfferVisible = false;
        _autoResumeGate.reset();
        _pendingAutoResume = false;
      } else if (e.statusCode == 504 || _ingestHangTripped) {
        final stage = uploadStage.trim();
        _pendingAutoResume = _armAutoResumeAfterTimeout(stageHint: stage);
        if (!_pendingAutoResume) {
          resumeOfferVisible = await _draftResumable();
        }
      }
      final stage = uploadStage.trim();
      if (e.statusCode == 504 && stage.isNotEmpty) {
        error = '${e.message} ($stage)';
      } else {
        error = e.message;
      }
      await _notify.showFailed(message: error!);
      await _refreshLibraryAfterIngestFail();
      return null;
    } catch (e) {
      error = e.toString();
      await _notify.showFailed(message: error!);
      await _refreshLibraryAfterIngestFail();
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
      if (_pendingAutoResume) {
        _schedulePendingAutoResume();
      } else {
        unawaited(_refreshResumeOffer());
      }
      if (!_uploadPumpBusy) {
        unawaited(_pumpUploadQueue());
      }
    }
  }

  /// design/186 — sentinel meta.cache_id for whole-library backup packs.
  static const libraryBackupCacheId = 'libbackup01';

  /// Count local papers that have a session folder (eligible for backup).
  Future<int> countLocalBackupPapers() async {
    var n = 0;
    for (final e in papers) {
      final cid = e.id.trim();
      if (cid.isEmpty) continue;
      if (await _paperDisk.hasSession(cid)) n += 1;
    }
    return n;
  }

  /// Upload every local library paper into one 7-day transfer pack (`item/{cid}/…`).
  Future<bool> exportLibraryTransferPack() async {
    if (opening || uploading || reanalyzing) {
      error = '다른 작업 중입니다. 잠시 후 다시 시도해 주세요.';
      notifyListeners();
      return false;
    }
    uploading = true;
    uploadPercent = 0;
    uploadStage = '보관함 백업 만들기';
    error = null;
    notifyListeners();
    try {
      final files = <String, Uint8List>{};
      var paperN = 0;
      for (final entry in papers) {
        final cid = entry.id.trim();
        if (cid.isEmpty) continue;
        if (!await _paperDisk.hasSession(cid)) continue;
        final extra = await _collectUserArtifactPackFiles(cid);
        final leaf = await _paperDisk.collectTransferPackFiles(
          cid,
          extraFiles: extra,
        );
        if (!leaf.containsKey('session.json')) continue;
        for (final e in leaf.entries) {
          files['item/$cid/${e.key}'] = e.value;
        }
        paperN += 1;
      }
      if (paperN == 0 || files.isEmpty) {
        error = '백업할 로컬 논문이 없습니다.';
        return false;
      }
      var declared = 0;
      for (final b in files.values) {
        declared += b.length;
      }
      final created = await _client.createTransferPack(
        cacheId: libraryBackupCacheId,
        title: '보관함 백업 ($paperN건)',
        declaredBytes: declared,
      );
      final packId = '${created['pack_id'] ?? ''}'.trim();
      if (packId.isEmpty) {
        error = '보관함 백업을 만들지 못했습니다.';
        return false;
      }
      final st = await _client.fetchStatus();
      final piece = st.transferPackPieceMax;
      final manifest = <String, Map<String, dynamic>>{};
      var done = 0;
      for (final e in files.entries) {
        final bytes = e.value;
        final sha = paperDiskSha256Hex(bytes);
        final parts = (bytes.length + piece - 1) ~/ piece;
        if (parts <= 1) {
          await _client.putTransferPackFile(
            packId: packId,
            path: e.key,
            bytes: bytes,
          );
        } else {
          for (var i = 0; i < parts; i++) {
            final start = i * piece;
            final end = (start + piece > bytes.length)
                ? bytes.length
                : start + piece;
            await _client.putTransferPackFile(
              packId: packId,
              path: e.key,
              bytes: Uint8List.sublistView(bytes, start, end),
              partIndex: i,
              partTotal: parts,
              sha256: sha,
            );
          }
        }
        manifest[e.key] = {'size': bytes.length, 'sha256': sha};
        done += 1;
        uploadPercent = ((done / files.length) * 90).round().clamp(0, 90);
        uploadStage = '보관함 백업 업로드 $done/${files.length}';
        notifyListeners();
      }
      uploadStage = '보관함 백업 완료 처리';
      notifyListeners();
      await _client.completeTransferPack(packId: packId, files: manifest);
      uploadPercent = 100;
      uploadStage = '보관함 백업 준비됨 (7일)';
      asrEvidenceBus?.record(
        'transfer_pack_complete',
        ok: true,
        cacheId: libraryBackupCacheId,
        details: {
          'file_n': files.length,
          'bytes': declared,
          'paper_n': paperN,
          'library_bundle': true,
        },
      );
      return true;
    } on AsrApiException catch (e) {
      error = e.message;
      return false;
    } catch (e) {
      error = e.toString();
      return false;
    } finally {
      uploading = false;
      if (uploadPercent >= 100) {
        // keep stage briefly for snackbar
      } else {
        uploadPercent = 0;
        uploadStage = '';
      }
      notifyListeners();
    }
  }

  /// design/186 — list packs for import UI.
  Future<List<Map<String, dynamic>>> listTransferPacks() async {
    try {
      return await _client.listTransferPacks();
    } on AsrApiException catch (e) {
      error = e.message;
      notifyListeners();
      return const [];
    } catch (e) {
      error = e.toString();
      notifyListeners();
      return const [];
    }
  }

  /// design/186 — import pack → replace same cache_id locally (no cloud papers/).
  /// Library bundles use `item/{cache_id}/…` paths (settings whole-library backup).
  Future<bool> importTransferPack(
    String packId, {
    bool deleteAfter = true,
  }) async {
    if (opening || uploading || reanalyzing) {
      error = '다른 작업 중입니다. 잠시 후 다시 시도해 주세요.';
      notifyListeners();
      return false;
    }
    final pid = packId.trim();
    if (pid.isEmpty) return false;
    uploading = true;
    uploadPercent = 0;
    uploadStage = '백업된 보관함 논문 받기';
    error = null;
    notifyListeners();
    try {
      final lease = await _client.leaseTransferPack(pid);
      final meta = lease['meta'];
      final filesMeta = lease['files'];
      if (meta is! Map || filesMeta is! Map) {
        error = '백업 정보가 없습니다.';
        return false;
      }
      final cacheId = '${meta['cache_id'] ?? ''}'.trim();
      final title = '${meta['title'] ?? cacheId}'.trim();
      if (cacheId.isEmpty) {
        error = '백업 cache_id가 없습니다.';
        return false;
      }
      final st = await _client.fetchStatus();
      final piece = st.transferPackPieceMax;
      final files = <String, Uint8List>{};
      final entries = filesMeta.entries.toList();
      var i = 0;
      for (final ent in entries) {
        final rel = '${ent.key}'.trim();
        if (rel.isEmpty || ent.value is! Map) continue;
        final row = Map<String, dynamic>.from(ent.value as Map);
        final wantSha = '${row['sha256'] ?? ''}'.trim().toLowerCase();
        final wantSize = () {
          final v = row['size'];
          if (v is int) return v;
          if (v is num) return v.toInt();
          return int.tryParse('$v') ?? 0;
        }();
        final buf = BytesBuilder(copy: false);
        var offset = 0;
        while (true) {
          final chunk = await _client.getTransferPackFile(
            packId: pid,
            path: rel,
            offset: offset,
            limit: piece,
          );
          if (chunk.isEmpty) break;
          buf.add(chunk);
          offset += chunk.length;
          if (wantSize > 0 && offset >= wantSize) break;
          if (chunk.length < piece) break;
        }
        final bytes = buf.toBytes();
        if (wantSize > 0 && bytes.length != wantSize) {
          error = '파일 크기 불일치: $rel';
          return false;
        }
        final got = paperDiskSha256Hex(bytes);
        if (wantSha.isNotEmpty && got != wantSha) {
          error = '파일 검증 실패: $rel';
          return false;
        }
        files[rel] = Uint8List.fromList(bytes);
        i += 1;
        uploadPercent = ((i / entries.length) * 85).round().clamp(0, 85);
        uploadStage = '백업 다운로드 $i/${entries.length}';
        notifyListeners();
      }
      uploadStage = '로컬에 반영';
      notifyListeners();
      var byPaper = _groupTransferPackFiles(files);
      if (byPaper.isEmpty) {
        // Legacy single-paper pack (flat leaf paths + meta.cache_id).
        if (!files.containsKey('session.json')) {
          error = '가져올 논문 파일이 없습니다.';
          return false;
        }
        byPaper = {cacheId: files};
      }
      var applied = 0;
      for (final e in byPaper.entries) {
        final cid = e.key;
        final leaf = e.value;
        final paperTitle = _titleFromPackSession(leaf) ??
            (byPaper.length == 1 && title.isNotEmpty ? title : cid);
        final ok = await _paperDisk.replaceFromTransferPack(
          cacheId: cid,
          title: paperTitle,
          files: leaf,
        );
        if (!ok) {
          error = '로컬 반영에 실패했습니다 ($cid).';
          return false;
        }
        await _restoreUserArtifactsFromPack(cid, leaf);
        applied += 1;
      }
      if (deleteAfter) {
        try {
          await _client.deleteTransferPack(pid);
        } catch (_) {}
      }
      uploadPercent = 100;
      uploadStage = applied > 1
          ? '백업된 보관함 논문 $applied건 가져오기 완료'
          : '백업된 보관함 논문 가져오기 완료';
      await refresh();
      asrEvidenceBus?.record(
        'transfer_pack_download',
        ok: true,
        cacheId: cacheId,
        details: {
          'file_n': files.length,
          'paper_n': applied,
          'library_bundle': byPaper.length > 1 ||
              cacheId == libraryBackupCacheId,
        },
      );
      return true;
    } on AsrApiException catch (e) {
      error = e.message;
      return false;
    } catch (e) {
      error = e.toString();
      return false;
    } finally {
      uploading = false;
      if (uploadPercent < 100) {
        uploadPercent = 0;
        uploadStage = '';
      }
      notifyListeners();
    }
  }

  /// Flat pack → empty (caller uses meta.cache_id); `item/{cid}/…` → bundle.
  Map<String, Map<String, Uint8List>> _groupTransferPackFiles(
    Map<String, Uint8List> files,
  ) {
    final out = <String, Map<String, Uint8List>>{};
    for (final e in files.entries) {
      final rel = e.key.trim().replaceAll('\\', '/');
      if (!rel.startsWith('item/')) continue;
      final rest = rel.substring('item/'.length);
      final slash = rest.indexOf('/');
      if (slash <= 0) continue;
      final cid = rest.substring(0, slash).trim();
      final leaf = rest.substring(slash + 1).trim();
      if (cid.isEmpty || leaf.isEmpty) continue;
      out.putIfAbsent(cid, () => <String, Uint8List>{})[leaf] = e.value;
    }
    return out;
  }

  String? _titleFromPackSession(Map<String, Uint8List> leaf) {
    final raw = leaf['session.json'];
    if (raw == null || raw.isEmpty) return null;
    try {
      final map = jsonDecode(utf8.decode(raw));
      if (map is! Map) return null;
      final t = '${map['title'] ?? ''}'.trim();
      return t.isEmpty ? null : t;
    } catch (_) {
      return null;
    }
  }

  /// design/187 E — bookmarks/annotations paper slice + shadowing disk files.
  Future<Map<String, Uint8List>> _collectUserArtifactPackFiles(
    String cacheId,
  ) async {
    final out = <String, Uint8List>{};
    final bm = _bookmarks?.exportPaperPackBytes(cacheId);
    if (bm != null && bm.isNotEmpty) {
      out['user/bookmarks.json'] = bm;
    }
    final ann = _annotations?.exportPaperPackBytes(cacheId);
    if (ann != null && ann.isNotEmpty) {
      out['user/annotations.json'] = ann;
    }
    if (_diskUid != null) {
      _shadowDisk.bindUid(_diskUid);
      out.addAll(await _shadowDisk.listPackFiles(cacheId));
    }
    return out;
  }

  Future<void> _restoreUserArtifactsFromPack(
    String cacheId,
    Map<String, Uint8List> files,
  ) async {
    final restored = await _paperDisk.restoreUserArtifactPackFiles(
      cacheId: cacheId,
      files: files,
      applyShadowing: (cid, shadow) => _shadowDisk.applyPackFiles(cid, shadow),
    );
    final bm = restored.bookmarks;
    if (bm != null && bm.isNotEmpty) {
      try {
        final raw = jsonDecode(utf8.decode(bm));
        if (raw is Map) {
          await _bookmarks?.importPaperPackJson(
            cacheId,
            Map<String, dynamic>.from(raw),
          );
        }
      } catch (_) {}
    }
    final ann = restored.annotations;
    if (ann != null && ann.isNotEmpty) {
      try {
        final raw = jsonDecode(utf8.decode(ann));
        if (raw is Map) {
          await _annotations?.importPaperPackJson(
            cacheId,
            Map<String, dynamic>.from(raw),
          );
        }
      } catch (_) {}
    }
  }

}
