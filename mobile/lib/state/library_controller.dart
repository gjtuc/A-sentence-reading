/// Paper library state for the Flutter shell (design/62).
library;

import 'package:flutter/foundation.dart';

import '../api/client.dart';
import '../api/paper_models.dart';

/// Loads `/api/cache/papers` and opens a cache entry into [opened].
class LibraryController extends ChangeNotifier {
  LibraryController({required AsrClient client}) : _client = client;

  final AsrClient _client;

  List<PaperEntry> papers = const [];
  OpenedPaper? opened;
  bool loading = false;
  bool opening = false;
  String? error;

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

  Future<OpenedPaper?> open(PaperEntry entry) async {
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
      // Prefer list title if open payload omits it.
      opened = o.title.isEmpty
          ? OpenedPaper(
              sessionId: o.sessionId,
              cacheId: o.cacheId.isEmpty ? entry.id : o.cacheId,
              title: entry.title,
              sentenceCount: o.sentenceCount,
              figureCount: o.figureCount,
              warnings: o.warnings,
            )
          : o;
      return opened;
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

  void clearOpened() {
    opened = null;
    notifyListeners();
  }

  void clearAll() {
    papers = const [];
    opened = null;
    error = null;
    loading = false;
    opening = false;
    notifyListeners();
  }
}
