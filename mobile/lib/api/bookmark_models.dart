/// Reader bookmark store — stable keys + merge (GCS sync).
library;

const kBookmarksStoreVersion = 1;
const kBookmarksPrefsKey = 'asr.bookmarks.v1';

/// One bookmark event (latest [at] wins on merge; [deleted] removes).
class BookmarkEvent {
  const BookmarkEvent({required this.at, this.deleted = false});

  final String at;
  final bool deleted;

  Map<String, dynamic> toJson() => {
        'at': at,
        if (deleted) 'deleted': true,
      };

  static BookmarkEvent? fromJson(Object? raw) {
    if (raw is! Map) return null;
    final at = raw['at'];
    if (at is! String || at.trim().isEmpty) return null;
    final deleted = raw['deleted'] == true;
    return BookmarkEvent(at: at, deleted: deleted);
  }
}

/// Per-paper bookmark maps (raw events — use [activeKeys] for UI).
class PaperBookmarks {
  const PaperBookmarks({
    this.sentences = const {},
    this.figures = const {},
  });

  final Map<String, BookmarkEvent> sentences;
  final Map<String, BookmarkEvent> figures;

  Set<String> get activeSentenceKeys => activeKeys(sentences);
  Set<String> get activeFigureKeys => activeKeys(figures);

  int get totalActiveCount =>
      activeSentenceKeys.length + activeFigureKeys.length;

  static Set<String> activeKeys(Map<String, BookmarkEvent> events) {
    return events.entries
        .where((e) => !e.value.deleted)
        .map((e) => e.key)
        .toSet();
  }

  PaperBookmarks copyWith({
    Map<String, BookmarkEvent>? sentences,
    Map<String, BookmarkEvent>? figures,
  }) {
    return PaperBookmarks(
      sentences: sentences ?? this.sentences,
      figures: figures ?? this.figures,
    );
  }

  Map<String, dynamic> toJson() => {
        'sentences': {
          for (final e in sentences.entries) e.key: e.value.toJson(),
        },
        'figures': {
          for (final e in figures.entries) e.key: e.value.toJson(),
        },
      };

  static PaperBookmarks fromJson(Object? raw) {
    if (raw is! Map) return const PaperBookmarks();
    return PaperBookmarks(
      sentences: _parseMap(raw['sentences']),
      figures: _parseMap(raw['figures']),
    );
  }

  static Map<String, BookmarkEvent> _parseMap(Object? raw) {
    if (raw is! Map) return {};
    final out = <String, BookmarkEvent>{};
    for (final entry in raw.entries) {
      final key = entry.key.toString().trim();
      if (key.isEmpty) continue;
      final ev = BookmarkEvent.fromJson(entry.value);
      if (ev != null) out[key] = ev;
    }
    return out;
  }
}

class BookmarksStore {
  const BookmarksStore({
    this.version = kBookmarksStoreVersion,
    this.papers = const {},
  });

  final int version;
  final Map<String, PaperBookmarks> papers;

  BookmarksStore copyWith({Map<String, PaperBookmarks>? papers}) {
    return BookmarksStore(version: version, papers: papers ?? this.papers);
  }

  Map<String, dynamic> toJson() => {
        'version': version,
        'papers': {
          for (final e in papers.entries) e.key: e.value.toJson(),
        },
      };

  static BookmarksStore empty() => const BookmarksStore();

  static BookmarksStore fromJson(Object? raw) {
    if (raw is! Map) return BookmarksStore.empty();
    final ver = raw['version'];
    if (ver is! int || ver != kBookmarksStoreVersion) {
      return BookmarksStore.empty();
    }
    final papersRaw = raw['papers'];
    if (papersRaw is! Map) {
      return const BookmarksStore();
    }
    final papers = <String, PaperBookmarks>{};
    for (final entry in papersRaw.entries) {
      final key = entry.key.toString().trim();
      if (key.isEmpty) continue;
      papers[key] = PaperBookmarks.fromJson(entry.value);
    }
    return BookmarksStore(papers: papers);
  }
}

String bookmarkPaperKey(String cacheId) => 'cache:${cacheId.trim()}';

String bookmarksPrefsKey(String? uid) {
  final u = (uid ?? '').trim().replaceAll(RegExp(r'[^A-Za-z0-9_\-]'), '');
  if (u.isEmpty) return kBookmarksPrefsKey;
  final safe = u.length > 128 ? u.substring(0, 128) : u;
  return '$kBookmarksPrefsKey.u.$safe';
}

BookmarkEvent bookmarkEventNow({bool deleted = false}) {
  return BookmarkEvent(
    at: DateTime.now().toUtc().toIso8601String(),
    deleted: deleted,
  );
}

/// Merge event maps — latest [at] per key wins.
Map<String, BookmarkEvent> mergeBookmarkEvents(
  Map<String, BookmarkEvent> a,
  Map<String, BookmarkEvent> b,
) {
  final out = Map<String, BookmarkEvent>.from(a);
  for (final entry in b.entries) {
    final prev = out[entry.key];
    if (prev == null || entry.value.at.compareTo(prev.at) >= 0) {
      out[entry.key] = entry.value;
    }
  }
  return out;
}

PaperBookmarks mergePaperBookmarks(PaperBookmarks a, PaperBookmarks b) {
  return PaperBookmarks(
    sentences: mergeBookmarkEvents(a.sentences, b.sentences),
    figures: mergeBookmarkEvents(a.figures, b.figures),
  );
}

BookmarksStore mergeBookmarksStores(BookmarksStore a, BookmarksStore b) {
  final keys = {...a.papers.keys, ...b.papers.keys};
  final papers = <String, PaperBookmarks>{};
  for (final key in keys) {
    final pa = a.papers[key] ?? const PaperBookmarks();
    final pb = b.papers[key] ?? const PaperBookmarks();
    final merged = mergePaperBookmarks(pa, pb);
    if (merged.activeSentenceKeys.isNotEmpty ||
        merged.activeFigureKeys.isNotEmpty ||
        merged.sentences.isNotEmpty ||
        merged.figures.isNotEmpty) {
      papers[key] = merged;
    }
  }
  return BookmarksStore(papers: papers);
}

/// Prune empty paper rows only (keep delete tombstones for sync).
PaperBookmarks compactPaperBookmarks(PaperBookmarks paper) => paper;

BookmarksStore compactBookmarksStore(BookmarksStore store) {
  final papers = <String, PaperBookmarks>{};
  for (final entry in store.papers.entries) {
    if (entry.value.sentences.isNotEmpty || entry.value.figures.isNotEmpty) {
      papers[entry.key] = entry.value;
    }
  }
  return BookmarksStore(papers: papers);
}
