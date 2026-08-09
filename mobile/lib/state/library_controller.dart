/// Paper library + opened reading session (design/62 · design/63 · design/70 · design/71).
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

  /// Backward-compatible alias used by older reader scaffolding.
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
      if (o.cacheId.isEmpty) {
        // cache_id should come from server; keep entry id as display fallback only
      }
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

  /// Sentence step — never changes figureIndex (PRODUCT invariant).
  Future<void> advanceSentence(int delta) async {
    final s = session;
    if (s == null || !s.isValid) return;
    final beforeFig = s.figureIndex;
    s.advanceSentence(delta);
    assert(s.figureIndex == beforeFig, 'figure index must stay put');
    notifyListeners();
    await _syncCursor(sentence: true);
  }

  /// Figure step — never changes sentenceIndex (PRODUCT invariant).
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
    } catch (_) {
      // EDGE: offline / 404 — UI already updated; sync is best-effort.
    }
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
    // WHY (MULTI-USER): next account must not resume previous user's job/PDF.
    await _drafts.clear();
    notifyListeners();
  }

  static String sha256Hex(Uint8List bytes) {
    return sha256.convert(bytes).toString();
  }

  /// design/71 — on library open: auto reattach processing job or retry local draft.
  Future<IngestJobResult?> resumePendingIfAny() async {
    if (uploading) return null;
    final draft = await _drafts.read();
    if (draft == null) return null;

    if (draft.canReattach) {
      return _finishWithPoll(draft);
    }

    // A (minimal): local PDF still on disk → auto re-POST without user pick.
    if (draft.localPath.isNotEmpty) {
      final raw = await _drafts.readLocalPdf(draft.localPath);
      if (raw == null || raw.isEmpty) {
        await _drafts.clear();
        return null;
      }
      final bytes = Uint8List.fromList(raw);
      final hash = sha256Hex(bytes);
      if (hash != draft.contentHash) {
        // EDGE: corrupted draft — wipe, never upload wrong bytes as success.
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
    return null;
  }

  /// Same-file pick: if draft hash matches, reattach or reuse bytes path.
  Future<IngestJobResult?> uploadPdf({
    required String filename,
    required Uint8List bytes,
    String? knownHash,
  }) async {
    if (uploading) {
      // WHY: one-at-a-time chip — overlapping uploads confuse progress + list.
      error = '이미 업로드 중입니다.';
      notifyListeners();
      return null;
    }

    final hash = knownHash ?? sha256Hex(bytes);
    final existing = await _drafts.read();
    // WHY: user re-picked same PDF → auto resume (product decision).
    if (existing != null &&
        existing.contentHash == hash &&
        existing.canReattach) {
      return _finishWithPoll(existing);
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
      );
      await _drafts.write(draft);

      final started = await _client.startIngestPdfBytes(
        filename: filename,
        bytes: bytes,
      );
      draft = draft.copyWith(jobId: started.jobId, phase: 'processing');
      await _drafts.write(draft);
      uploadPercent = 1;
      uploadStage = '업로드 완료, 처리 중';
      notifyListeners();

      final result = await _client.pollIngestJob(
        jobId: started.jobId,
        onProgress: (pct, msg) {
          uploadPercent = pct;
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
      error = e.message;
      // Keep draft for auto/same-file resume — do not clear on failure.
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
      // EDGE: 404 after GCS miss — clear stuck draft so user can start clean.
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
