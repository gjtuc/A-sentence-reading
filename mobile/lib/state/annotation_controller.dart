/// Reader annotation state — local cache + GCS sync (design/166).
library;

import 'dart:async';

import 'package:flutter/foundation.dart';

import '../api/annotation_gate.dart';
import '../api/annotation_models.dart';
import '../api/annotation_plain.dart';
import '../api/annotation_store.dart';
import '../api/figure_ink_models.dart';
import '../api/client.dart';
import '../api/reader_nav_labels.dart';
import '../api/reading_models.dart';
import '../api/rich_sentence.dart';

class AnnotationController extends ChangeNotifier {
  AnnotationController({AsrClient? client}) : _client = client;

  AsrClient? _client;
  String? _uid;
  String? _cacheId;
  PaperAnnotations _paper = const PaperAnnotations();
  AnnotationsStore _store = AnnotationsStore.empty();
  bool serverAvailable = false;
  bool ready = false;
  bool figureInkMode = false;
  FigureInkTool figureInkTool = FigureInkTool.pen;
  String figureInkColor = kDefaultFigureInkColor;
  Timer? _pushTimer;

  /// design/182 — color → drag paint mode (sentence-scoped).
  bool sentencePaintMode = false;
  String? paintColor;
  String? paintSentenceKey;
  int? paintSentenceIndex;
  int? paintPreviewStart;
  int? paintPreviewEnd;

  bool get canAnnotate => _uid != null;
  int get activeCount => _paper.totalActiveCount;

  void attachClient(AsrClient client) => _client = client;

  Future<void> bindUid(String? uid) async {
    _uid = (uid ?? '').trim().isEmpty ? null : uid!.trim();
    _store = await loadAnnotationsStore(uid: _uid);
    _reloadPaperFromStore();
    ready = true;
    notifyListeners();
  }

  void clearSession() {
    _uid = null;
    _cacheId = null;
    _paper = const PaperAnnotations();
    _store = AnnotationsStore.empty();
    figureInkMode = false;
    figureInkTool = FigureInkTool.pen;
    figureInkColor = kDefaultFigureInkColor;
    clearSentencePaint(notify: false);
    _pushTimer?.cancel();
    ready = false;
    notifyListeners();
  }

  void setServerAvailable(bool next) {
    if (serverAvailable == next) return;
    serverAvailable = next;
    notifyListeners();
  }

  Future<void> loadPaper(String cacheId) async {
    final cid = cacheId.trim();
    if (cid.isEmpty) return;
    _cacheId = cid;
    _store = await loadAnnotationsStore(uid: _uid);
    _reloadPaperFromStore();
    notifyListeners();
  }

  Future<void> applyNavPrune({
    required SectionNavIndex sectionNav,
    required FigureNavIndex figureNav,
  }) async {
    if (_cacheId == null) return;
    final pruned = prunePaperAnnotations(
      paper: _paper,
      sectionNav: sectionNav,
      figureNav: figureNav,
    );
    if (pruned.sentences.length == _paper.sentences.length &&
        pruned.figures.length == _paper.figures.length &&
        pruned.totalActiveCount == _paper.totalActiveCount) {
      return;
    }
    _paper = pruned;
    await _persistPaper();
    notifyListeners();
  }

  Future<void> pullFromServer() async {
    final client = _client;
    if (client == null || _uid == null || !serverAvailable) return;
    try {
      final remote = await client.fetchAnnotationsSync();
      if (!remote.available || remote.store == null) return;
      final remoteStore = AnnotationsStore.fromJson(remote.store);
      _store = mergeAnnotationsStores(_store, remoteStore);
      await saveAnnotationsStore(uid: _uid, store: _store);
      _reloadPaperFromStore();
      notifyListeners();
    } catch (_) {
      // EDGE: offline — keep local.
    }
  }

  Future<void> pushToServer() async {
    final client = _client;
    if (client == null || _uid == null || !serverAvailable) return;
    try {
      final result = await client.pushAnnotationsSync(_store.toJson());
      if (!result.available || result.store == null) return;
      _store = AnnotationsStore.fromJson(result.store);
      await saveAnnotationsStore(uid: _uid, store: _store);
      _reloadPaperFromStore();
      notifyListeners();
    } catch (_) {
      // EDGE: retry on next lifecycle.
    }
  }

  void schedulePush() {
    _pushTimer?.cancel();
    _pushTimer = Timer(const Duration(milliseconds: 500), () {
      unawaited(pushToServer());
    });
  }

  List<AnnotationEvent> activeForSentenceKey(String? key) {
    if (key == null || key.isEmpty) return const [];
    return _paper.activeEventsForSentenceKey(key);
  }

  List<AnnotationEvent> activeForFigureKey(String? key) {
    if (key == null || key.isEmpty) return const [];
    return _paper.activeEventsForFigureKey(key);
  }

  List<AnnotationEvent> allActiveSentenceEvents() {
    final out = <AnnotationEvent>[];
    for (final list in _paper.sentences.values) {
      out.addAll(list.where((e) => e.isActive));
    }
    return out;
  }

  Iterable<MapEntry<String, List<AnnotationEvent>>> get sentenceAnnotationEntries =>
      _paper.sentences.entries;

  Future<void> upsertHighlight({
    required String sentenceKey,
    required String sentenceId,
    required String color,
    String note = '',
    String? existingId,
    Map<String, dynamic>? selector,
    List<int>? charRange,
  }) async {
    final events = Map<String, List<AnnotationEvent>>.from(_paper.sentences);
    final list = List<AnnotationEvent>.from(events[sentenceKey] ?? const []);
    final id = existingId ?? newAnnotationId();
    final idx = list.indexWhere((e) => e.id == id);
    final preservedRange =
        charRange ?? (idx >= 0 ? list[idx].charRange : null);
    final preservedSelector =
        selector ?? (idx >= 0 ? list[idx].selector : null);
    final ev = annotationEventNow(
      id: id,
      color: color,
      note: note,
      sentenceId: sentenceId,
      selector: preservedSelector,
      charRange: preservedRange,
    );
    if (idx >= 0) {
      list[idx] = ev;
    } else {
      list.add(ev);
    }
    events[sentenceKey] = list.where((e) => e.isActive).toList();
    _paper = _paper.copyWith(sentences: events);
    await _persistPaper();
    schedulePush();
    notifyListeners();
  }

  /// design/182 — new partial highlight (always new id, non-null range).
  Future<bool> addPartialHighlight({
    required String sentenceKey,
    required String sentenceId,
    required String color,
    required String plain,
    required int start,
    required int end,
    String note = '',
  }) async {
    final range = clampCharRange(start, end, plain.length);
    if (range == null) return false;
    final selector = textQuoteSelectorForRange(plain, range[0], range[1]);
    final events = Map<String, List<AnnotationEvent>>.from(_paper.sentences);
    final list = List<AnnotationEvent>.from(events[sentenceKey] ?? const []);
    list.add(
      annotationEventNow(
        id: newAnnotationId(),
        color: color,
        note: note,
        sentenceId: sentenceId,
        charRange: range,
        selector: selector,
      ),
    );
    events[sentenceKey] = list.where((e) => e.isActive).toList();
    _paper = _paper.copyWith(sentences: events);
    await _persistPaper();
    schedulePush();
    notifyListeners();
    return true;
  }

  /// Update color/note on an existing event; keep char_range.
  Future<void> updateHighlightMeta({
    required String sentenceKey,
    required String existingId,
    required String color,
    String note = '',
  }) async {
    final events = Map<String, List<AnnotationEvent>>.from(_paper.sentences);
    final list = List<AnnotationEvent>.from(events[sentenceKey] ?? const []);
    final idx = list.indexWhere((e) => e.id == existingId);
    if (idx < 0) return;
    final prev = list[idx];
    list[idx] = annotationEventNow(
      id: prev.id,
      color: color,
      note: note,
      sentenceId: prev.sentenceId,
      charRange: prev.charRange,
      selector: prev.selector,
    );
    events[sentenceKey] = list.where((e) => e.isActive).toList();
    _paper = _paper.copyWith(sentences: events);
    await _persistPaper();
    schedulePush();
    notifyListeners();
  }

  Future<void> removeAnnotationById({
    required String sentenceKey,
    required String id,
  }) async {
    final events = Map<String, List<AnnotationEvent>>.from(_paper.sentences);
    final list = List<AnnotationEvent>.from(events[sentenceKey] ?? const []);
    final idx = list.indexWhere((e) => e.id == id);
    if (idx < 0) return;
    final prev = list[idx];
    list[idx] = annotationEventNow(
      id: prev.id,
      deleted: true,
      sentenceId: prev.sentenceId,
    );
    events[sentenceKey] = list;
    _paper = _paper.copyWith(sentences: events);
    await _persistPaper();
    schedulePush();
    notifyListeners();
  }

  void armSentencePaint({
    required String color,
    required String sentenceKey,
    required int sentenceIndex,
  }) {
    figureInkMode = false;
    sentencePaintMode = true;
    paintColor = color;
    paintSentenceKey = sentenceKey;
    paintSentenceIndex = sentenceIndex;
    paintPreviewStart = null;
    paintPreviewEnd = null;
    notifyListeners();
  }

  void clearSentencePaint({bool notify = true}) {
    if (!sentencePaintMode &&
        paintColor == null &&
        paintSentenceKey == null &&
        paintPreviewStart == null) {
      return;
    }
    sentencePaintMode = false;
    paintColor = null;
    paintSentenceKey = null;
    paintSentenceIndex = null;
    paintPreviewStart = null;
    paintPreviewEnd = null;
    if (notify) notifyListeners();
  }

  void setPaintPreview(int? start, int? end) {
    paintPreviewStart = start;
    paintPreviewEnd = end;
    notifyListeners();
  }

  bool isPaintingSentence(String? key) =>
      sentencePaintMode &&
      key != null &&
      key.isNotEmpty &&
      paintSentenceKey == key;

  Future<void> removeAnnotationsForKey(String sentenceKey) async {
    final events = Map<String, List<AnnotationEvent>>.from(_paper.sentences);
    final list = List<AnnotationEvent>.from(events[sentenceKey] ?? const []);
    if (list.isEmpty) return;
    final tombstones = list
        .map((e) => annotationEventNow(id: e.id, deleted: true, sentenceId: e.sentenceId))
        .toList();
    events[sentenceKey] = tombstones;
    _paper = _paper.copyWith(sentences: events);
    await _persistPaper();
    schedulePush();
    notifyListeners();
  }

  Future<void> addFigureInkPath({
    required String figureKey,
    required List<List<double>> points,
    String? color,
    double width = 2.0,
  }) async {
    final events = Map<String, List<AnnotationEvent>>.from(_paper.figures);
    final list = List<AnnotationEvent>.from(events[figureKey] ?? const []);
    final id = newAnnotationId();
    final inkColor = (color ?? figureInkColor).trim();
    list.add(
      annotationEventNow(
        id: id,
        kind: 'ink',
        color: inkColor,
        paths: [
          {
            'color': inkColor,
            'width': width,
            'points': points,
          },
        ],
      ),
    );
    events[figureKey] = list.where((e) => e.isActive).toList();
    _paper = _paper.copyWith(figures: events);
    await _persistPaper();
    schedulePush();
    notifyListeners();
  }

  /// Erase the nearest ink stroke at normalized coords (figure panel).
  Future<bool> eraseFigureInkNear({
    required String figureKey,
    required double nx,
    required double ny,
    double threshold = 0.045,
  }) async {
    final list = _paper.activeEventsForFigureKey(figureKey);
    final id = inkEventIdNearPoint(
      events: list,
      nx: nx,
      ny: ny,
      threshold: threshold,
    );
    if (id == null) return false;
    final events = Map<String, List<AnnotationEvent>>.from(_paper.figures);
    final raw = List<AnnotationEvent>.from(events[figureKey] ?? const []);
    final idx = raw.indexWhere((e) => e.id == id);
    if (idx < 0) return false;
    raw[idx] = annotationEventNow(id: id, deleted: true, kind: 'ink');
    events[figureKey] = raw;
    _paper = _paper.copyWith(figures: events);
    await _persistPaper();
    schedulePush();
    notifyListeners();
    return true;
  }

  void setFigureInkTool(FigureInkTool next) {
    if (figureInkTool == next) return;
    figureInkTool = next;
    notifyListeners();
  }

  void setFigureInkColor(String hex) {
    final h = hex.trim();
    if (h.isEmpty || figureInkColor == h) return;
    figureInkColor = h;
    figureInkTool = FigureInkTool.pen;
    notifyListeners();
  }

  void toggleFigureInkMode() {
    figureInkMode = !figureInkMode;
    if (figureInkMode) {
      figureInkTool = FigureInkTool.pen;
      clearSentencePaint(notify: false);
    }
    notifyListeners();
  }

  Future<void> reanchorToSession(ReadingSession session) async {
    final nav = session.sectionNav;
    final sentences = session.sentences;
    final byId = {for (final s in sentences) s.id: s};
    final keyToSid = <String, String>{};
    for (var i = 0; i < sentences.length; i++) {
      final key = nav.sentenceBookmarkKeyForGlobal(i);
      if (key != null) keyToSid[key] = sentences[i].id;
    }

    final updated = <String, List<AnnotationEvent>>{};
    for (final entry in _paper.sentences.entries) {
      final key = entry.key;
      final out = <AnnotationEvent>[];
      for (final ev in entry.value) {
        if (!ev.isActive) continue;
        var next = ev;
        final sid = ev.sentenceId;
        SentenceView? matched;
        String status = 'ok';
        if (sid.isNotEmpty && byId.containsKey(sid)) {
          matched = byId[sid];
          status = 'ok';
        } else if (nav.isValidSentenceBookmarkKey(key)) {
          final newSid = keyToSid[key] ?? sid;
          matched = byId[newSid];
          status = 'reanchored_by_key';
          next = next.copyWith(sentenceId: newSid);
        } else {
          final selectorHit = _selectorHit(ev.selector, sentences);
          if (selectorHit != null) {
            matched = selectorHit;
            status = 'reanchored_by_selector';
            next = next.copyWith(sentenceId: selectorHit.id);
          } else {
            out.add(next.copyWith(status: 'orphaned'));
            continue;
          }
        }
        if (matched != null && next.charRange != null) {
          final plain = annotationPlainForSentence(matched.text);
          final rebuilt = charRangeFromSelectorExact(plain, next.selector);
          if (rebuilt != null) {
            next = next.copyWith(charRange: rebuilt, status: status);
          } else {
            final cr = clampCharRange(
              next.charRange![0],
              next.charRange![1],
              plain.length,
            );
            if (cr == null) {
              out.add(next.copyWith(status: 'orphaned'));
              continue;
            }
            next = next.copyWith(charRange: cr, status: status);
          }
        } else {
          next = next.copyWith(status: status);
        }
        out.add(next);
      }
      if (out.isNotEmpty) updated[key] = out;
    }
    _paper = _paper.copyWith(sentences: updated);
    await _persistPaper();
    schedulePush();
    notifyListeners();
  }

  Future<void> purgePaper(String cacheId) async {
    await purgePaperAnnotations(uid: _uid, cacheId: cacheId);
    if (_cacheId == cacheId.trim()) {
      _paper = const PaperAnnotations();
    }
    _store = await loadAnnotationsStore(uid: _uid);
    notifyListeners();
  }

  void _reloadPaperFromStore() {
    final cid = _cacheId;
    if (cid == null || cid.isEmpty) {
      _paper = const PaperAnnotations();
      return;
    }
    _paper = _store.papers[annotationPaperKey(cid)] ?? const PaperAnnotations();
  }

  Future<void> _persistPaper() async {
    final cid = _cacheId;
    if (cid == null || cid.isEmpty) return;
    final pk = annotationPaperKey(cid);
    final papers = Map<String, PaperAnnotations>.from(_store.papers);
    if (_paper.sentences.isEmpty && _paper.figures.isEmpty) {
      papers.remove(pk);
    } else {
      papers[pk] = compactPaperAnnotations(_paper);
    }
    _store = AnnotationsStore(papers: papers);
    await saveAnnotationsStore(uid: _uid, store: _store);
  }

  static SentenceView? _selectorHit(
    Map<String, dynamic>? selector,
    List<SentenceView> sentences,
  ) {
    if (selector == null) return null;
    final exact = '${selector['exact'] ?? ''}'.trim();
    if (exact.isEmpty) return null;
    final needle = plainFromRichHtml(exact).toLowerCase();
    for (final s in sentences) {
      if (plainFromRichHtml(s.text).toLowerCase().contains(needle)) {
        return s;
      }
    }
    return null;
  }
}
