/// Paper library + opened reading session (design/62 · design/63).
library;

import 'package:flutter/foundation.dart';

import '../api/client.dart';
import '../api/paper_models.dart';
import '../api/reading_models.dart';

/// Loads `/api/cache/papers`, opens a cache entry, advances cursors independently.
class LibraryController extends ChangeNotifier {
  LibraryController({required AsrClient client}) : _client = client;

  final AsrClient _client;

  List<PaperEntry> papers = const [];
  ReadingSession? session;
  bool loading = false;
  bool opening = false;
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

  void clearAll() {
    papers = const [];
    session = null;
    error = null;
    loading = false;
    opening = false;
    notifyListeners();
  }
}
