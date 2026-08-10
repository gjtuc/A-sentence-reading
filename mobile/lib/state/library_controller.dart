/// Paper library + opened reading session (design/62 · 70 · 71 · 72).
library;

import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';

import '../api/client.dart';
import '../api/ingest_models.dart';
import '../api/paper_models.dart';
import '../api/reading_models.dart';
import '../api/upload_draft_models.dart';
import '../api/upload_draft_store.dart';

/// Loads `/api/cache/papers`, opens a cache entry, advances cursors independently.
class LibraryController extends ChangeNotifier {
  LibraryController({
    required AsrClient client,
    UploadDraftStore? draftStore,
  })  : _client = client,
        _drafts = draftStore ?? PrefsUploadDraftStore();

  final AsrClient _client;
  final UploadDraftStore _drafts;

  List<PaperEntry> papers = const [];
  ReadingSession? session;
  bool loading = false;
  bool opening = false;
  bool uploading = false;
  int uploadPercent = 0;
  String uploadStage = '';
  String? error;

  ReadingSession? get opened => session;

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
    if (s == null) return;
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
    await _drafts.clear();
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

    if (draft.localPath.isEmpty) return null;
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

    // Same-file re-pick / auto: resume chunks only after prefix integrity OK.
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
          // EDGE: prior chunks failed integrity — wipe and start clean.
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
    notifyListeners();
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
            uploadPercent = pct;
            uploadStage = msg.isEmpty ? '조각 올리는 중' : msg;
            notifyListeners();
          },
          onUploadId: (upl) async {
            // Persist before chunks so force-stop can integrity-resume.
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
        // Kill switch ASR_CHUNKED_UPLOAD=0 → 503; fall back to multipart.
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
      uploadPercent = 50;
      uploadStage = '처리 중';
      notifyListeners();

      final result = await _client.pollIngestJob(
        jobId: jobId,
        onProgress: (pct, msg) {
          uploadPercent = 50 + (pct.clamp(0, 100) ~/ 2);
          uploadStage = msg.isEmpty ? '처리 중' : msg;
          notifyListeners();
        },
      );
      await _drafts.clear();
      await refresh();
      final seen = papers.any((p) => p.id == result.cacheId);
      if (!seen) {
        error = '업로드는 끝났지만 목록에 아직 없습니다. 새로고침해 주세요.';
        notifyListeners();
        return null;
      }
      return result;
    } on AsrApiException catch (e) {
      if (e.statusCode == 409) {
        // Integrity failure — do not keep a poisoned chunk session.
        await _drafts.clear();
      }
      error = e.message;
      return null;
    } catch (e) {
      error = e.toString();
      return null;
    } finally {
      uploading = false;
      uploadPercent = 0;
      uploadStage = '';
      notifyListeners();
    }
  }

  Future<IngestJobResult?> _finishWithPoll(UploadDraft draft) async {
    uploading = true;
    uploadPercent = 0;
    uploadStage = '이어올리는 중';
    error = null;
    notifyListeners();
    try {
      final result = await _client.pollIngestJob(
        jobId: draft.jobId,
        onProgress: (pct, msg) {
          uploadPercent = pct;
          uploadStage = msg.isEmpty ? '이어올리는 중' : msg;
          notifyListeners();
        },
      );
      await _drafts.clear();
      await refresh();
      final seen = papers.any((p) => p.id == result.cacheId);
      if (!seen) {
        error = '업로드는 끝났지만 목록에 아직 없습니다. 새로고침해 주세요.';
        notifyListeners();
        return null;
      }
      return result;
    } on AsrApiException catch (e) {
      if (e.statusCode == 404) {
        await _drafts.clear();
      }
      error = e.message;
      return null;
    } catch (e) {
      error = e.toString();
      return null;
    } finally {
      uploading = false;
      uploadPercent = 0;
      uploadStage = '';
      notifyListeners();
    }
  }
}
