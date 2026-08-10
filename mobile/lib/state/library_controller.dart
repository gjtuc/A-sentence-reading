/// Paper library + opened reading session (design/62 · 70 · 71 · 72 · 74 · 75).
library;

import 'dart:async';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';

import '../api/client.dart';
import '../api/ingest_models.dart';
import '../api/paper_models.dart';
import '../api/reading_models.dart';
import '../api/upload_draft_models.dart';
import '../api/upload_draft_store.dart';
import '../api/upload_notify.dart';

/// Stall after this long without progress while an upload is marked active.
const Duration kUploadStallAfter = Duration(seconds: 45);

/// Loads `/api/cache/papers`, opens a cache entry, advances cursors independently.
class LibraryController extends ChangeNotifier {
  LibraryController({
    required AsrClient client,
    UploadDraftStore? draftStore,
    UploadNotify? uploadNotify,
  })  : _client = client,
        _drafts = draftStore ?? PrefsUploadDraftStore(),
        _notify = uploadNotify ?? createUploadNotify();

  final AsrClient _client;
  final UploadDraftStore _drafts;
  final UploadNotify _notify;

  List<PaperEntry> papers = const [];
  ReadingSession? session;
  bool loading = false;
  bool opening = false;
  bool uploading = false;
  int uploadPercent = 0;
  String uploadStage = '';
  String? error;

  /// design/74 — set when notification permission blocked but upload continues.
  String? uploadBackgroundHint;

  /// design/75 — true when progress heartbeat went silent (honest interrupt UI).
  bool uploadStalled = false;

  DateTime? _lastProgressAt;
  Timer? _stallWatch;
  bool _resumeInFlight = false;

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

  Future<UploadNotifyStart> _maybeStartNotify(String stage) async {
    if (!await _backgroundNotifyEnabled()) {
      return const UploadNotifyStart(active: false);
    }
    return _notify.startUploading(stage: stage);
  }

  void _touchProgress() {
    _lastProgressAt = DateTime.now();
    if (uploadStalled) {
      uploadStalled = false;
    }
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
      papers = await _client.listPapers();
    } on AsrApiException catch (e) {
      error = e.message;
      papers = const [];
    } catch (e) {
      error = e.toString();
      papers = const [];
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<ReadingSession?> open(PaperEntry entry) async {
    if (!entry.isValid) {
      error = '잘못된 보관 항목입니다.';
      notifyListeners();
      return null;
    }
    opening = true;
    error = null;
    notifyListeners();
    try {
      final o = await _client.openPaper(entry.id);
      if (o.title.isEmpty) o.title = entry.title;
      session = o;
      return session;
    } on AsrApiException catch (e) {
      error = e.message;
      return null;
    } catch (e) {
      error = e.toString();
      return null;
    } finally {
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
  }

  Future<void> advanceFigure(int delta) async {
    final s = session;
    if (s == null || !s.isValid) return;
    final beforeSent = s.sentenceIndex;
    s.advanceFigure(delta);
    assert(s.sentenceIndex == beforeSent, 'sentence index must stay put');
    notifyListeners();
    await _syncCursor(figure: true);
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

  void clearOpened() {
    session = null;
    notifyListeners();
  }

  Future<void> clearAll() async {
    papers = const [];
    session = null;
    error = null;
    loading = false;
    opening = false;
    uploading = false;
    uploadPercent = 0;
    uploadStage = '';
    uploadBackgroundHint = null;
    await _drafts.clear();
    await _notify.stop();
    _stopStallWatch();
    notifyListeners();
  }

  static String sha256Hex(Uint8List bytes) => sha256.convert(bytes).toString();

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
    _startStallWatch();
    notifyListeners();

    // design/74 — product 1A: notify when enabled; upload continues either way.
    final startedNotify = await _maybeStartNotify('준비 중');
    if (startedNotify.permissionDeniedHint) {
      uploadBackgroundHint =
          '알림·백그라운드 권한이 없어 업로드가 중간에 끊길 수 있습니다.';
      notifyListeners();
    }

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
        final started = await _client.startIngestPdfBytesChunked(
          filename: filename,
          bytes: bytes,
          contentHash: hash,
          existingUploadId: resumeUploadId,
          onProgress: (pct, msg) {
            _touchProgress();
            uploadPercent = pct;
            uploadStage = msg.isEmpty ? '조각 올리는 중' : msg;
            notifyListeners();
            unawaited(
              _notify.updateProgress(
                percent: uploadPercent,
                stage: uploadStage,
              ),
            );
          },
          onUploadId: (upl) async {
            draft = draft.copyWith(uploadId: upl, phase: 'uploading');
            await _drafts.write(draft);
          },
        );
        jobId = started.jobId;
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
        );
        jobId = started.jobId;
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
      notifyListeners();
      await _notify.updateProgress(percent: 50, stage: '처리 중');

      final result = await _client.pollIngestJob(
        jobId: jobId,
        onProgress: (pct, msg) {
          _touchProgress();
          uploadPercent = 50 + (pct.clamp(0, 100) ~/ 2);
          uploadStage = msg.isEmpty ? '처리 중' : msg;
          notifyListeners();
          unawaited(
            _notify.updateProgress(
              percent: uploadPercent,
              stage: uploadStage,
            ),
          );
        },
      );
      await _drafts.clear();
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
    } on AsrApiException catch (e) {
      if (e.statusCode == 409) {
        await _drafts.clear();
      }
      error = e.message;
      await _notify.showFailed(message: e.message);
      return null;
    } catch (e) {
      error = e.toString();
      await _notify.showFailed(message: error!);
      return null;
    } finally {
      uploading = false;
      uploadPercent = 0;
      uploadStage = '';
      _stopStallWatch();
      notifyListeners();
    }
  }

  Future<IngestJobResult?> _finishWithPoll(UploadDraft draft) async {
    uploading = true;
    uploadPercent = 0;
    uploadStage = '이어올리는 중';
    error = null;
    uploadBackgroundHint = null;
    _startStallWatch();
    notifyListeners();
    final startedNotify = await _maybeStartNotify('이어올리는 중');
    if (startedNotify.permissionDeniedHint) {
      uploadBackgroundHint =
          '알림·백그라운드 권한이 없어 업로드가 중간에 끊길 수 있습니다.';
      notifyListeners();
    }
    try {
      final result = await _client.pollIngestJob(
        jobId: draft.jobId,
        onProgress: (pct, msg) {
          _touchProgress();
          uploadPercent = pct;
          uploadStage = msg.isEmpty ? '이어올리는 중' : msg;
          notifyListeners();
          unawaited(
            _notify.updateProgress(
              percent: uploadPercent,
              stage: uploadStage,
            ),
          );
        },
      );
      await _drafts.clear();
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
    } on AsrApiException catch (e) {
      if (e.statusCode == 404) {
        await _drafts.clear();
      }
      error = e.message;
      await _notify.showFailed(message: e.message);
      return null;
    } catch (e) {
      error = e.toString();
      await _notify.showFailed(message: error!);
      return null;
    } finally {
      uploading = false;
      uploadPercent = 0;
      uploadStage = '';
      _stopStallWatch();
      notifyListeners();
    }
  }
}
