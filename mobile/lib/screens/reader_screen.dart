import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/cite_refs.dart' as cite;
import '../api/client.dart';
import '../api/document_citation.dart';
import '../api/fig_refs.dart' as fig;
import '../api/figure_pinch_sensitivity.dart';
import '../api/figure_swipe_gate.dart';
import '../api/reading_models.dart';
import '../api/rich_sentence.dart';
import '../state/cite_panel_controller.dart';
import '../state/bookmark_controller.dart';
import '../api/annotation_models.dart';
import '../state/annotation_controller.dart';
import '../state/library_controller.dart';
import '../state/shadowing_controller.dart';
import '../state/translate_controller.dart';
import '../state/tts_controller.dart';
import 'shadowing_practice_screen.dart';
import '../api/reader_nav_labels.dart';
import '../widgets/reader_nav_picker.dart';
import '../widgets/annotation_toolbar_sheet.dart';
import '../widgets/annotation_list_sheet.dart';
import '../widgets/annotated_sentence_text.dart';
import 'figure_edit_screen.dart';

/// Split reader: sentence panel + figure panel (design/63) + TTS (design/64).
///
/// INVARIANT: sentence controls never call figure advance and vice versa.
/// TTS never mutates cursors.
/// design/97 — double-tap a panel to fill the screen; double-tap again to restore.
/// design/98 — drag the split bar; magnet at default; edge tension → full-panel snap.
/// design/100 — single tap toggles panel chrome; split mode syncs both frames.
enum _ReaderLayoutMode { split, sentenceOnly, figureOnly }

class ReaderScreen extends StatefulWidget {
  const ReaderScreen({
    super.key,
    required this.library,
    required this.tts,
    required this.client,
    required this.shadowing,
    required this.translate,
    required this.citePanel,
    required this.bookmarks,
    required this.annotations,
  });

  final LibraryController library;
  final TtsController tts;
  final AsrClient client;
  final ShadowingController shadowing;
  final TranslateController translate;
  final CitePanelController citePanel;
  final BookmarkController bookmarks;
  final AnnotationController annotations;

  @override
  State<ReaderScreen> createState() => _ReaderScreenState();
}

class _ReaderScreenState extends State<ReaderScreen> {
  static const double _kDefaultFraction = 0.6;
  /// Soft resistance band around default (fraction of height).
  static const double _kMagnetResistanceBand = 0.11;
  /// Pull this far from default → break free to 1:1 tracking (jelly snap).
  static const double _kMagnetEscape = 0.038;
  /// On release, snap to default when still within this distance.
  static const double _kMagnetReleaseSnap = 0.022;
  /// Min drag factor at default (slow pulls still move the bar).
  static const double _kMagnetMinFactor = 0.2;
  static const double _kEdgeSnap = 0.14;
  static const double _kHardMin = 0.02;
  static const double _kHardMax = 0.98;
  static const double _kSplitBar = 16;

  _ReaderLayoutMode _layout = _ReaderLayoutMode.split;
  double _sentenceFraction = _kDefaultFraction;
  bool _dragging = false;
  bool _inMagnet = false;
  bool _magnetEscaped = false;
  bool _edgePreviewSentence = false;
  bool _edgePreviewFigure = false;
  /// design/100 — shared chrome for sentence + figure headers.
  bool _chromeVisible = true;
  /// design/114 — reset split when a different paper is opened.
  String? _layoutSessionKey;
  /// design/124 — server kill `fig_ref_hints=false` hides chips; missing/error → show.
  bool _figRefHints = true;
  /// design/131 — server kill `caption_full_text=false` restores 2-line …; missing → full.
  bool _captionFullText = true;
  /// design/149 — caption baked into PNG; hide under-image Text when true.
  bool _figureCaptionInImage = true;

  @override
  void initState() {
    super.initState();
    widget.client.fetchStatus().then((st) {
      if (!mounted) return;
      // WHY: explicit false is the kill switch; do not invent a hide on status miss.
      setState(() {
        _figRefHints = st.figRefHints;
        _captionFullText = st.captionFullText;
        _figureCaptionInImage =
            st.mobileFigureCaptionInImage && st.figureCaptionInImage;
      });
    }).catchError((_) {
      // EDGE: status unreachable → keep full captions + chips (fail-open for readability).
    });
  }

  void _ensureLayoutForSession(ReadingSession s) {
    final key = '${s.sessionId}|${s.cacheId}';
    if (_layoutSessionKey == key) return;
    _layoutSessionKey = key;
    _layout = _ReaderLayoutMode.split;
    _sentenceFraction = _kDefaultFraction;
    _chromeVisible = true;
    _dragging = false;
    _inMagnet = false;
    _magnetEscaped = false;
    _edgePreviewSentence = false;
    _edgePreviewFigure = false;
  }

  void _toggleChrome() {
    setState(() => _chromeVisible = !_chromeVisible);
  }

  void _toggleSentenceExpand() {
    setState(() {
      if (_layout == _ReaderLayoutMode.sentenceOnly) {
        _layout = _ReaderLayoutMode.split;
        _sentenceFraction = _kDefaultFraction;
      } else {
        _layout = _ReaderLayoutMode.sentenceOnly;
      }
      _edgePreviewSentence = false;
      _edgePreviewFigure = false;
    });
  }

  void _toggleFigureExpand() {
    setState(() {
      if (_layout == _ReaderLayoutMode.figureOnly) {
        _layout = _ReaderLayoutMode.split;
        _sentenceFraction = _kDefaultFraction;
      } else {
        _layout = _ReaderLayoutMode.figureOnly;
      }
      _edgePreviewSentence = false;
      _edgePreviewFigure = false;
    });
  }

  String _qualityBannerMessage(ReadingSession s) {
    final w = s.warnings.where((x) => x.isNotEmpty).toList();
    if (w.isEmpty) {
      return '분석 품질에 주의가 필요합니다. 재분석을 권장합니다.';
    }
    return '분석 품질: ${w.take(3).join(' · ')}';
  }

  /// design/156 — full-screen vertical swipe (split restore stays double-tap).
  void _swipeToSentenceFromFigure() {
    setState(() {
      if (_layout != _ReaderLayoutMode.figureOnly) return;
      _layout = _ReaderLayoutMode.sentenceOnly;
      _edgePreviewSentence = false;
      _edgePreviewFigure = false;
    });
  }

  void _swipeToFigureFromSentence() {
    setState(() {
      if (_layout != _ReaderLayoutMode.sentenceOnly) return;
      _layout = _ReaderLayoutMode.figureOnly;
      _edgePreviewSentence = false;
      _edgePreviewFigure = false;
    });
  }

  void _onSplitDragStart() {
    setState(() {
      _dragging = true;
      _magnetEscaped = false;
      _layout = _ReaderLayoutMode.split;
    });
  }

  void _onSplitDragUpdate(double deltaDy, double totalH) {
    if (totalH <= _kSplitBar + 1) return;
    final usable = totalH - _kSplitBar;
    setState(() {
      _dragging = true;
      _layout = _ReaderLayoutMode.split;
      final nearEdge = _sentenceFraction < _kEdgeSnap ||
          _sentenceFraction > 1 - _kEdgeSnap;
      final edgeScale = nearEdge ? 0.32 : 1.0;
      final rawDelta = (deltaDy / usable) * edgeScale;

      double next;
      if (_magnetEscaped) {
        next =
            (_sentenceFraction + rawDelta).clamp(_kHardMin, _kHardMax);
        _inMagnet = false;
      } else {
        final dist = (_sentenceFraction - _kDefaultFraction).abs();
        final inBand = dist <= _kMagnetResistanceBand;
        if (inBand) {
          final t = (dist / _kMagnetResistanceBand).clamp(0.0, 1.0);
          final resistance =
              _kMagnetMinFactor + (1.0 - _kMagnetMinFactor) * t * t;
          next = (_sentenceFraction + rawDelta * resistance)
              .clamp(_kHardMin, _kHardMax);
          final newDist = (next - _kDefaultFraction).abs();
          _inMagnet = newDist <= _kMagnetResistanceBand;
          final projected =
              (_sentenceFraction + rawDelta - _kDefaultFraction).abs();
          if (newDist >= _kMagnetEscape || projected >= _kMagnetEscape) {
            _magnetEscaped = true;
            _inMagnet = false;
            next = (_sentenceFraction + rawDelta).clamp(_kHardMin, _kHardMax);
            HapticFeedback.lightImpact();
          }
        } else {
          next =
              (_sentenceFraction + rawDelta).clamp(_kHardMin, _kHardMax);
          _inMagnet = false;
        }
      }

      _sentenceFraction = next;
      _edgePreviewSentence = next >= 1 - _kEdgeSnap;
      _edgePreviewFigure = next <= _kEdgeSnap;
    });
  }

  void _onSplitDragEnd() {
    setState(() {
      _dragging = false;
      _magnetEscaped = false;
      if (_sentenceFraction >= 1 - _kEdgeSnap) {
        _layout = _ReaderLayoutMode.sentenceOnly;
        _sentenceFraction = _kDefaultFraction;
      } else if (_sentenceFraction <= _kEdgeSnap) {
        _layout = _ReaderLayoutMode.figureOnly;
        _sentenceFraction = _kDefaultFraction;
      } else if ((_sentenceFraction - _kDefaultFraction).abs() <=
          _kMagnetReleaseSnap) {
        _sentenceFraction = _kDefaultFraction;
        _layout = _ReaderLayoutMode.split;
      } else {
        _layout = _ReaderLayoutMode.split;
      }
      _edgePreviewSentence = false;
      _edgePreviewFigure = false;
      _inMagnet = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final library = widget.library;
    final tts = widget.tts;
    final client = widget.client;
    final shadowing = widget.shadowing;
    final translate = widget.translate;
    return AnimatedBuilder(
      animation: Listenable.merge([
        library,
        tts,
        translate,
        widget.citePanel,
        widget.bookmarks,
        widget.annotations,
      ]),
      builder: (context, _) {
        final s = library.session;
        if (s == null || !s.isValid) {
          return const Center(
            child: Padding(
              padding: EdgeInsets.all(24),
              child: Text(
                'No paper open. Open one from Library\n'
                '(sentence + figure + TTS).',
                textAlign: TextAlign.center,
              ),
            ),
          );
        }
        _ensureLayoutForSession(s);
        final showKo = translate.enabled;
        final showSentence = _layout != _ReaderLayoutMode.figureOnly;
        final showFigure = _layout != _ReaderLayoutMode.sentenceOnly;
        return Column(
          children: [
            if (library.showIngestQualityBanner)
              MaterialBanner(
                content: Text(
                  _qualityBannerMessage(s),
                ),
                leading: const Icon(Icons.info_outline),
                actions: [
                  TextButton(
                    onPressed: () async {
                      final entry = library.paperEntryForCacheId(s.cacheId);
                      if (entry != null) {
                        await library.reanalyzePaper(entry);
                      }
                    },
                    child: const Text('재분석'),
                  ),
                  TextButton(
                    onPressed: library.dismissIngestQualityBanner,
                    child: const Text('닫기'),
                  ),
                ],
              ),
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      s.title.isEmpty ? '(no title)' : s.title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.titleSmall,
                    ),
                  ),
                  if (widget.annotations.activeCount > 0)
                    IconButton(
                      tooltip: '주석 목록',
                      onPressed: () => showAnnotationListSheet(
                        context: context,
                        session: s,
                        annotations: widget.annotations,
                        library: library,
                      ),
                      icon: Badge(
                        label: Text('${widget.annotations.activeCount}'),
                        child: const Icon(Icons.notes_outlined, size: 20),
                      ),
                    ),
                  if (shadowing.enabled)
                    TextButton(
                      onPressed: !shadowing.serverAvailable
                          ? null
                          : () async {
                              await shadowing.recordPracticePressed();
                              if (!context.mounted) return;
                              Navigator.of(context).push(
                                MaterialPageRoute<void>(
                                  builder: (_) => ShadowingPracticeScreen(
                                    client: client,
                                    library: library,
                                    shadowing: shadowing,
                                    tts: tts,
                                  ),
                                ),
                              );
                            },
                      child: const Text('연습'),
                    ),
                ],
              ),
            ),
            if (library.shadowingChunksBusy)
              const Padding(
                padding: EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                child: Text(
                  '연습 구간을 준비하는 중…',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 12),
                ),
              ),
            if (library.shadowingChunksError != null)
              Padding(
                padding: const EdgeInsets.fromLTRB(12, 4, 12, 0),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        library.shadowingChunksError!,
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.error,
                          fontSize: 12,
                        ),
                      ),
                    ),
                    TextButton(
                      onPressed: library.shadowingChunksBusy
                          ? null
                          : () => library.retryShadowingChunks(),
                      child: const Text('다시 시도'),
                    ),
                  ],
                ),
              ),
            Expanded(
              child: LayoutBuilder(
                builder: (context, constraints) {
                  final h = constraints.maxHeight;
                  final showBar = showSentence && showFigure;
                  final bar = showBar ? _kSplitBar : 0.0;
                  final usable = (h - bar).clamp(0.0, h);
                  late final double sentenceH;
                  late final double figureH;
                  if (!showSentence) {
                    sentenceH = 0;
                    figureH = h;
                  } else if (!showFigure) {
                    sentenceH = h;
                    figureH = 0;
                  } else {
                    sentenceH = usable * _sentenceFraction;
                    figureH = usable - sentenceH;
                  }
                  final animMs = _dragging ? 0 : 280;
                  return Stack(
                    children: [
                      Column(
                        children: [
                          // design/115 — NEVER put clipBehavior on Container/
                          // AnimatedContainer without decoration: Flutter does
                          // decoration! and the whole reader body goes blank
                          // (title-only). ClipRect keeps hard edges safely.
                          ClipRect(
                            child: AnimatedContainer(
                              duration: Duration(milliseconds: animMs),
                              curve: Curves.easeInOut,
                              height: sentenceH,
                              child: sentenceH < 1
                                  ? const SizedBox.shrink()
                                  : _SentencePanel(
                                      library: library,
                                      tts: tts,
                                      client: client,
                                      session: s,
                                      citePanel: widget.citePanel,
                                      bookmarks: widget.bookmarks,
                                      annotations: widget.annotations,
                                      showKo: showKo,
                                      showChrome: _chromeVisible,
                                      figRefHints: _figRefHints,
                                      onToggleChrome: _toggleChrome,
                                      onDoubleTapExpand: _toggleSentenceExpand,
                                      onSwipeToFigure: _layout ==
                                              _ReaderLayoutMode.sentenceOnly
                                          ? _swipeToFigureFromSentence
                                          : null,
                                    ),
                            ),
                          ),
                          if (showBar)
                            _SplitHandle(
                              height: _kSplitBar,
                              magnetActive: _inMagnet,
                              edgePreviewSentence: _edgePreviewSentence,
                              edgePreviewFigure: _edgePreviewFigure,
                              onDragStart: _onSplitDragStart,
                              onDragUpdate: (dy) =>
                                  _onSplitDragUpdate(dy, h),
                              onDragEnd: _onSplitDragEnd,
                            ),
                          ClipRect(
                            child: AnimatedContainer(
                              duration: Duration(milliseconds: animMs),
                              curve: Curves.easeInOut,
                              height: figureH,
                              child: figureH < 1
                                  ? const SizedBox.shrink()
                                  : _FigurePanel(
                                      library: library,
                                      client: client,
                                      session: s,
                                      bookmarks: widget.bookmarks,
                                      annotations: widget.annotations,
                                      showKo: showKo,
                                      showChrome: _chromeVisible,
                                      captionFullText: _captionFullText,
                                      figureCaptionInImage: _figureCaptionInImage,
                                      onToggleChrome: _toggleChrome,
                                      onDoubleTapExpand: _toggleFigureExpand,
                                      onSwipeToSentence: _layout ==
                                              _ReaderLayoutMode.figureOnly
                                          ? _swipeToSentenceFromFigure
                                          : null,
                                      onLongPressEdit: () {
                                        final cid = s.cacheId.trim();
                                        if (cid.isEmpty) return;
                                        var hasSource = false;
                                        for (final p in library.papers) {
                                          if (p.id == cid) {
                                            hasSource = p.hasSource;
                                            break;
                                          }
                                        }
                                        Navigator.of(context).push(
                                          MaterialPageRoute<void>(
                                            builder: (_) => FigureEditScreen(
                                              client: client,
                                              cacheId: cid,
                                              hasSource: hasSource,
                                              editStash: library.editStash,
                                            ),
                                          ),
                                        );
                                      },
                                    ),
                            ),
                          ),
                        ],
                      ),
                      // Smart guide: default split position while near magnet.
                      if (showBar && (_inMagnet || _dragging))
                        Positioned(
                          top: usable * _kDefaultFraction,
                          left: 24,
                          right: 24,
                          child: IgnorePointer(
                            child: AnimatedOpacity(
                              duration: const Duration(milliseconds: 120),
                              opacity: _inMagnet ? 1 : 0.35,
                              child: Container(
                                height: 2,
                                decoration: BoxDecoration(
                                  color: Theme.of(context)
                                      .colorScheme
                                      .primary
                                      .withOpacity(_inMagnet ? 0.85 : 0.4),
                                  borderRadius: BorderRadius.circular(1),
                                ),
                              ),
                            ),
                          ),
                        ),
                    ],
                  );
                },
              ),
            ),
          ],
        );
      },
    );
  }
}

/// design/98 — draggable split bar with magnet / edge-snap affordances.
class _SplitHandle extends StatelessWidget {
  const _SplitHandle({
    required this.height,
    required this.onDragStart,
    required this.onDragUpdate,
    required this.onDragEnd,
    this.magnetActive = false,
    this.edgePreviewSentence = false,
    this.edgePreviewFigure = false,
  });

  final double height;
  final VoidCallback onDragStart;
  final ValueChanged<double> onDragUpdate;
  final VoidCallback onDragEnd;
  final bool magnetActive;
  final bool edgePreviewSentence;
  final bool edgePreviewFigure;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    Color barColor = scheme.outlineVariant;
    if (magnetActive) {
      barColor = scheme.primary;
    } else if (edgePreviewSentence || edgePreviewFigure) {
      barColor = scheme.tertiary;
    }
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onVerticalDragStart: (_) => onDragStart(),
      onVerticalDragUpdate: (d) => onDragUpdate(d.delta.dy),
      onVerticalDragEnd: (_) => onDragEnd(),
      onVerticalDragCancel: onDragEnd,
      child: SizedBox(
        height: height,
        width: double.infinity,
        child: Center(
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 120),
            width: magnetActive ? 72 : 48,
            height: 4,
            decoration: BoxDecoration(
              color: barColor,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
        ),
      ),
    );
  }
}

class _SentencePanel extends StatelessWidget {
  const _SentencePanel({
    required this.library,
    required this.tts,
    required this.client,
    required this.session,
    required this.citePanel,
    required this.bookmarks,
    required this.annotations,
    required this.showKo,
    required this.showChrome,
    this.figRefHints = true,
    this.onToggleChrome,
    this.onDoubleTapExpand,
    this.onSwipeToFigure,
  });

  final LibraryController library;
  final TtsController tts;
  final AsrClient client;
  final ReadingSession session;
  final CitePanelController citePanel;
  final BookmarkController bookmarks;
  final AnnotationController annotations;
  final bool showKo;
  final bool showChrome;
  /// design/124 — from /api/status; parent owns fetch.
  final bool figRefHints;
  final VoidCallback? onToggleChrome;
  final VoidCallback? onDoubleTapExpand;
  /// design/156 — sentence full-screen: swipe up → figure full-screen.
  final VoidCallback? onSwipeToFigure;

  @override
  Widget build(BuildContext context) {
    final cur = session.currentSentence;
    final header = session.sentenceCount == 0
        ? const SectionHeaderParts(sectionName: 'no sentences', position: 0, total: 0)
        : session.sectionNav.headerPartsFor(session.sentenceIndex);
    final canPick = session.sentenceCount > 0 && session.sectionNav.sectionCount > 0;
    final sentKey =
        session.sectionNav.sentenceBookmarkKeyForGlobal(session.sentenceIndex);
    final sentHighlighted = bookmarks.isSentenceBookmarked(sentKey);
    final sectionBadge =
        bookmarks.sectionBadgeCount(session.sectionNav, session.sentenceIndex);
    final bodyWarn = session.warnings.any((w) => w.startsWith('high_body_ratio'));
    final headerLeft = header.sectionName.isEmpty
        ? 'Sentence'
        : (header.sectionName.toLowerCase() == 'body' && bodyWarn
            ? '${header.sectionName} ⚠'
            : header.sectionName);
    final bookmarkHints = BookmarkPickerHints(
      leftBadgeCount: (i) =>
          bookmarks.pickerSectionBadgeCount(session.sectionNav, i),
      rightHighlighted: (left, right) => bookmarks.pickerSentenceHighlighted(
        session.sectionNav,
        left,
        right,
      ),
    );
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          AnimatedSize(
            duration: const Duration(milliseconds: 180),
            curve: Curves.easeInOut,
            alignment: Alignment.topCenter,
            child: showChrome
                ? Row(
                    children: [
                      IconButton(
                        tooltip: 'prev sentence',
                        onPressed: session.sentenceCount == 0
                            ? null
                            : () async {
                                await tts.stop();
                                await library.advanceSentence(-1);
                              },
                        icon: const Icon(Icons.chevron_left),
                      ),
                      Expanded(
                        child: ReaderNavHeaderLabel(
                          left: headerLeft,
                          right: session.sentenceCount == 0
                              ? '— / —'
                              : header.rightLabel,
                          enabled: session.sentenceCount > 0,
                          highlighted: sentHighlighted,
                          leftBadgeCount: sectionBadge,
                          onTap: session.sentenceCount == 0
                              ? null
                              : () => _handleSentenceBookmarkTap(
                                    context,
                                    bookmarks: bookmarks,
                                    session: session,
                                  ),
                          onLongPress: canPick
                              ? () async {
                                  final idx = await showSectionNavPicker(
                                    context: context,
                                    nav: session.sectionNav,
                                    currentGlobalIndex: session.sentenceIndex,
                                    bookmarks: bookmarkHints,
                                  );
                                  if (idx == null) return;
                                  await tts.stop();
                                  await library.goToSentenceIndex(idx);
                                }
                              : null,
                        ),
                      ),
                      IconButton(
                        tooltip: 'next sentence',
                        onPressed: session.sentenceCount == 0
                            ? null
                            : () async {
                                await tts.stop();
                                await library.advanceSentence(1);
                              },
                        icon: const Icon(Icons.chevron_right),
                      ),
                      if (tts.loading)
                        const SizedBox(
                          width: 24,
                          height: 24,
                          child: Padding(
                            padding: EdgeInsets.all(4),
                            child: CircularProgressIndicator(strokeWidth: 2),
                          ),
                        )
                      else
                        IconButton(
                          tooltip: tts.playing ? 'stop TTS' : 'play TTS',
                          onPressed: (cur == null || !cur.hasText)
                              ? null
                              : () async {
                                  if (tts.playing) {
                                    await tts.stop();
                                  } else {
                                    await tts.playCurrentSentence();
                                  }
                                },
                          icon: Icon(
                            tts.playing
                                ? Icons.stop_circle_outlined
                                : Icons.volume_up,
                          ),
                        ),
                    ],
                  )
                : const SizedBox(width: double.infinity),
          ),
          if (showChrome && tts.error != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Text(
                tts.error!,
                style: TextStyle(
                  color: Theme.of(context).colorScheme.error,
                  fontSize: 12,
                ),
                textAlign: TextAlign.center,
              ),
            ),
          Expanded(
            child: Card(
              child: _SwipePager(
                enabled: session.sentenceCount > 0,
                // design/95+143 — swipe left → next, swipe right → prev
                onPrevious: () async {
                  await tts.stop();
                  await library.advanceSentence(-1);
                },
                onNext: () async {
                  await tts.stop();
                  await library.advanceSentence(1);
                },
                onTap: onToggleChrome,
                onDoubleTap: onDoubleTapExpand,
                onSwipeUp: onSwipeToFigure,
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: SingleChildScrollView(
                    child: cur == null || !cur.hasText
                        ? const Text('No sentence at this index.')
                        : GestureDetector(
                            onLongPress: () => _handleSentenceAnnotateLongPress(
                              context,
                              annotations: annotations,
                              session: session,
                              library: library,
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                if (cur.isUngrounded)
                                  Padding(
                                    padding: const EdgeInsets.only(bottom: 8),
                                    child: Chip(
                                      label: const Text('원문 미확인'),
                                      backgroundColor: Colors.amber.shade100,
                                      visualDensity: VisualDensity.compact,
                                    ),
                                  ),
                                AnnotatedSentenceText(
                                  html: cite.stripCiteMarkersForDisplay(cur.text),
                                  style: Theme.of(context).textTheme.titleMedium ??
                                      const TextStyle(fontSize: 18),
                                  annotations: annotations.activeForSentenceKey(sentKey),
                                ),
                                if (showKo && cur.textKo.trim().isNotEmpty) ...[
                                  const SizedBox(height: 12),
                                  richSentenceText(
                                    cite.stripCiteMarkersForDisplay(cur.textKo),
                                    style:
                                        Theme.of(context).textTheme.bodyMedium ??
                                            const TextStyle(fontSize: 14),
                                  ),
                                ],
                              ],
                            ),
                          ),
                  ),
                ),
              ),
            ),
          ),
          if (shouldShowThisPaperPanel(
            session: session,
            citePanelEnabled: citePanel.enabled,
            citePanelServerAvailable: citePanel.serverAvailable,
            thisPaperServerAvailable: citePanel.thisPaperServerAvailable,
          ))
            _ThisPaperPanel(
              client: client,
              citation: effectiveCitation(session),
            ),
          // design/139 — web-parity: dedicated chip row BELOW sentence frame (not inside body scroll).
          ..._figRefChipRow(context),
          if (citePanel.enabled && citePanel.serverAvailable)
            _CiteRefPanel(
              client: client,
              session: session,
            ),
        ],
      ),
    );
  }

  List<Widget> _figRefChipRow(BuildContext context) {
    // Kill: /api/status fig_ref_hints=false → no chips (design/124 · 139).
    if (!figRefHints) return const [];
    final cur = session.currentSentence;
    if (cur == null || !cur.hasText) return const [];
    final captions = session.figures.map((f) => f.caption).toList();
    final slotKeys = session.figures.map((f) => f.slotKey).toList();
    final hints = fig.hintsForSentence(
      text: cur.text,
      captions: captions,
      slotKeys: slotKeys,
      supplementaryMerged: session.supplementaryMerged,
    );
    if (hints.isEmpty) return const [];
    final scheme = Theme.of(context).colorScheme;
    return [
      Padding(
        padding: const EdgeInsets.fromLTRB(8, 6, 8, 2),
        child: Wrap(
          spacing: 6,
          runSpacing: 4,
          children: [
            for (final h in hints)
              OutlinedButton(
                style: OutlinedButton.styleFrom(
                  visualDensity: VisualDensity.compact,
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  // WHY: ghost chip like web .fig-ref-chip (transparent + border).
                  foregroundColor: h.figureIndex == session.figureIndex
                      ? scheme.onSurface
                      : scheme.onSurfaceVariant,
                  side: BorderSide(
                    color: h.figureIndex == session.figureIndex
                        ? scheme.outline
                        : scheme.outlineVariant,
                  ),
                  backgroundColor: Colors.transparent,
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
                onPressed: () {
                  // WHY: figure only — sentence index must stay (design/28 · 139).
                  library.goToFigureIndex(h.figureIndex);
                },
                child: Text(
                  '${h.ref} →',
                  style: const TextStyle(fontSize: 12, letterSpacing: 0.2),
                ),
              ),
          ],
        ),
      ),
    ];
  }
}

/// design/157 — single bibliographic row for the paper being read (Title 1/N).
class _ThisPaperPanel extends StatefulWidget {
  const _ThisPaperPanel({
    required this.client,
    required this.citation,
  });

  final AsrClient client;
  final DocumentCitation citation;

  @override
  State<_ThisPaperPanel> createState() => _ThisPaperPanelState();
}

class _ThisPaperPanelState extends State<_ThisPaperPanel> {
  bool _busy = false;
  String? _inlineError;

  Future<void> _open() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _inlineError = null;
    });
    try {
      final doi = widget.citation.doi.trim();
      if (doi.isNotEmpty) {
        final uri = Uri.parse('https://doi.org/$doi');
        final launched =
            await launchUrl(uri, mode: LaunchMode.externalApplication);
        if (!launched && mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('브라우저를 열 수 없습니다.')),
          );
        }
        return;
      }
      final result = await widget.client.resolveCite(widget.citation.text);
      if (!result.ok || result.url.isEmpty) {
        final msg = result.message.isNotEmpty
            ? result.message
            : (result.error.isNotEmpty ? result.error : 'resolve_failed');
        setState(() => _inlineError = msg);
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('이 논문 링크를 열 수 없습니다: $msg')),
          );
        }
        return;
      }
      final uri = Uri.tryParse(result.url);
      if (uri == null) {
        setState(() => _inlineError = 'bad_url');
        return;
      }
      final launched =
          await launchUrl(uri, mode: LaunchMode.externalApplication);
      if (!launched && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('브라우저를 열 수 없습니다.')),
        );
      }
    } catch (e) {
      setState(() => _inlineError = e.toString());
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('이 논문 링크 오류: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.citation.isVisible) return const SizedBox.shrink();
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(8, 4, 8, 2),
      child: Material(
        color: scheme.surfaceContainerHighest.withValues(alpha: 0.35),
        borderRadius: BorderRadius.circular(8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
              child: Text(
                '이 논문',
                style: Theme.of(context).textTheme.labelLarge,
              ),
            ),
            if (_inlineError != null)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 2),
                child: Text(
                  _inlineError!,
                  style: TextStyle(color: scheme.error, fontSize: 11),
                ),
              ),
            ListTile(
              dense: true,
              visualDensity: VisualDensity.compact,
              enabled: !_busy,
              leading: Icon(
                Icons.article_outlined,
                size: 20,
                color: scheme.onSurfaceVariant,
              ),
              title: Text(
                widget.citation.text,
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 12),
              ),
              subtitle: widget.citation.doi.isNotEmpty
                  ? Text(
                      'DOI ${widget.citation.doi}',
                      style: const TextStyle(fontSize: 10),
                    )
                  : null,
              onTap: _open,
            ),
          ],
        ),
      ),
    );
  }
}

/// design/148 — scrollable bibliography rows for current sentence cite numbers.
class _CiteRefPanel extends StatefulWidget {
  const _CiteRefPanel({
    required this.client,
    required this.session,
  });

  final AsrClient client;
  final ReadingSession session;

  @override
  State<_CiteRefPanel> createState() => _CiteRefPanelState();
}

class _CiteRefPanelState extends State<_CiteRefPanel> {
  int? _selectedN;
  int _sentenceIndex = -1;
  bool _busy = false;
  String? _inlineError;

  @override
  void initState() {
    super.initState();
    _sentenceIndex = widget.session.sentenceIndex;
  }

  @override
  void didUpdateWidget(covariant _CiteRefPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.session.sentenceIndex != _sentenceIndex) {
      _sentenceIndex = widget.session.sentenceIndex;
      _selectedN = null;
      _inlineError = null;
    }
  }

  Future<void> _openRow(cite.CiteRefEntry entry) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _selectedN = entry.n;
      _inlineError = null;
    });
    try {
      final result = await widget.client.resolveCite(entry.text);
      if (!result.ok || result.url.isEmpty) {
        final msg = result.message.isNotEmpty
            ? result.message
            : (result.error.isNotEmpty ? result.error : 'resolve_failed');
        setState(() => _inlineError = msg);
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('참고문헌 링크를 열 수 없습니다: $msg')),
          );
        }
        return;
      }
      final uri = Uri.tryParse(result.url);
      if (uri == null) {
        setState(() => _inlineError = 'bad_url');
        return;
      }
      final launched = await launchUrl(uri, mode: LaunchMode.externalApplication);
      if (!launched && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('브라우저를 열 수 없습니다.')),
        );
      }
    } catch (e) {
      setState(() => _inlineError = e.toString());
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('참고문헌 링크 오류: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final cur = widget.session.currentSentence;
    if (cur == null || !cur.hasText) return const SizedBox.shrink();
    final hints = cite.hintsForSentence(
      text: cur.text,
      bibliography: widget.session.references,
    );
    if (hints.isEmpty) return const SizedBox.shrink();

    final maxH = MediaQuery.sizeOf(context).height * 0.22;
    final scheme = Theme.of(context).colorScheme;

    return Padding(
      padding: const EdgeInsets.fromLTRB(8, 4, 8, 2),
      child: Material(
        color: scheme.surfaceContainerHighest.withValues(alpha: 0.35),
        borderRadius: BorderRadius.circular(8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
              child: Text(
                'References',
                style: Theme.of(context).textTheme.labelLarge,
              ),
            ),
            if (_inlineError != null)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 2),
                child: Text(
                  _inlineError!,
                  style: TextStyle(color: scheme.error, fontSize: 11),
                ),
              ),
            ConstrainedBox(
              constraints: BoxConstraints(maxHeight: maxH),
              child: ListView.separated(
                shrinkWrap: true,
                padding: const EdgeInsets.fromLTRB(4, 0, 4, 6),
                itemCount: hints.length,
                separatorBuilder: (_, __) => const Divider(height: 1),
                itemBuilder: (context, i) {
                  final h = hints[i];
                  final selected = _selectedN == h.n;
                  return ListTile(
                    dense: true,
                    visualDensity: VisualDensity.compact,
                    enabled: !_busy,
                    selected: selected,
                    leading: Text(
                      '[${h.n}]',
                      style: TextStyle(
                        fontWeight: FontWeight.w600,
                        color: selected ? scheme.primary : scheme.onSurface,
                      ),
                    ),
                    title: Text(
                      h.text,
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 12),
                    ),
                    onTap: () => _openRow(h),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _FigurePanel extends StatelessWidget {
  const _FigurePanel({
    required this.library,
    required this.client,
    required this.session,
    required this.bookmarks,
    required this.annotations,
    required this.showKo,
    required this.showChrome,
    this.captionFullText = true,
    this.figureCaptionInImage = true,
    this.onToggleChrome,
    this.onDoubleTapExpand,
    this.onLongPressEdit,
    this.onSwipeToSentence,
  });

  final LibraryController library;
  final AsrClient client;
  final ReadingSession session;
  final BookmarkController bookmarks;
  final AnnotationController annotations;
  final bool showKo;
  final bool showChrome;
  /// design/131 — false restores 2-line ellipsis (server kill / old clients).
  final bool captionFullText;
  /// design/149 — when true, caption is in PNG; hide Text under image.
  final bool figureCaptionInImage;
  final VoidCallback? onToggleChrome;
  final VoidCallback? onDoubleTapExpand;
  /// design/151 — long-press figure panel → overlay editor.
  final VoidCallback? onLongPressEdit;
  /// design/156 — figure full-screen: swipe down → sentence full-screen.
  final VoidCallback? onSwipeToSentence;

  @override
  Widget build(BuildContext context) {
    final cur = session.currentFigure;
    final header = session.figureCount == 0
        ? const FigureHeaderParts(
            kindLabel: 'no figures', numberLabel: '', totalLabel: '')
        : session.figureNav.headerPartsFor(
            session.figureIndex,
            totalFigures: session.figureCount,
          );
    final canPick =
        session.figureCount > 0 && session.figureNav.hasPicker;
    final figKey =
        session.figureNav.figureBookmarkKeyForCarousel(session.figureIndex);
    final figHighlighted = bookmarks.isFigureBookmarked(figKey);
    final kindBadge =
        bookmarks.kindBadgeCount(session.figureNav, session.figureIndex);
    final bookmarkHints = BookmarkPickerHints(
      leftBadgeCount: (i) => bookmarks.pickerKindBadgeCount(session.figureNav, i),
      rightHighlighted: (left, right) => bookmarks.pickerFigureHighlighted(
        session.figureNav,
        left,
        right,
      ),
    );
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          AnimatedSize(
            duration: const Duration(milliseconds: 180),
            curve: Curves.easeInOut,
            alignment: Alignment.topCenter,
            child: showChrome
                ? Row(
                    children: [
                      IconButton(
                        tooltip: 'prev figure',
                        onPressed: session.figureCount == 0
                            ? null
                            : () => library.advanceFigure(-1),
                        icon: const Icon(Icons.chevron_left),
                      ),
                      Expanded(
                        child: ReaderNavHeaderLabel(
                          left: header.kindLabel.isEmpty
                              ? 'Figure'
                              : header.kindLabel,
                          right: session.figureCount == 0
                              ? '— / —'
                              : header.rightLabel,
                          enabled: session.figureCount > 0,
                          highlighted: figHighlighted,
                          leftBadgeCount: kindBadge,
                          onTap: session.figureCount == 0
                              ? null
                              : () => _handleFigureBookmarkTap(
                                    context,
                                    bookmarks: bookmarks,
                                    session: session,
                                  ),
                          onLongPress: canPick
                              ? () async {
                                  final idx = await showFigureNavPicker(
                                    context: context,
                                    nav: session.figureNav,
                                    currentCarouselIndex: session.figureIndex,
                                    bookmarks: bookmarkHints,
                                  );
                                  if (idx == null) return;
                                  await library.goToFigureIndex(idx);
                                }
                              : null,
                        ),
                      ),
                      IconButton(
                        tooltip: 'next figure',
                        onPressed: session.figureCount == 0
                            ? null
                            : () => library.advanceFigure(1),
                        icon: const Icon(Icons.chevron_right),
                      ),
                      IconButton(
                        tooltip: annotations.figureInkMode ? '잉크 끄기' : '잉크',
                        onPressed: session.figureCount == 0
                            ? null
                            : () => annotations.toggleFigureInkMode(),
                        icon: Icon(
                          annotations.figureInkMode
                              ? Icons.draw
                              : Icons.draw_outlined,
                        ),
                      ),
                    ],
                  )
                : const SizedBox(width: double.infinity),
          ),
          Expanded(
            child: GestureDetector(
              behavior: HitTestBehavior.deferToChild,
              onLongPress: onLongPressEdit,
              child: Card(
                clipBehavior: Clip.antiAlias,
                child: cur == null
                  ? GestureDetector(
                      behavior: HitTestBehavior.opaque,
                      onTap: onToggleChrome,
                      child: const Center(child: Text('No figure.')),
                    )
                  : Column(
                      children: [
                        Expanded(
                          child: _FigureInkStack(
                            figureKey: figKey,
                            annotations: annotations,
                            child: _FigureImage(
                              src: cur.imageSrc,
                              swipeEnabled: session.figureCount > 0 && !annotations.figureInkMode,
                              onPrevious: () => library.advanceFigure(-1),
                              onNext: () => library.advanceFigure(1),
                              onTap: onToggleChrome,
                              onDoubleTapExpand: onDoubleTapExpand,
                              onSwipeToSentence: onSwipeToSentence,
                            ),
                          ),
                        ),
                        if (!figureCaptionInImage &&
                            (cur.caption.trim().isNotEmpty ||
                                (showKo && cur.captionKo.trim().isNotEmpty)))
                          // design/131 — full caption: wrap + scroll (no 2-line …).
                          // WHY ConstrainedBox: unbounded Column must not crush the image.
                          // Kill: when server sends caption_full_text=false, keep 2-line ellipsis.
                          Padding(
                            padding: const EdgeInsets.all(8),
                            child: ConstrainedBox(
                              constraints: BoxConstraints(
                                maxHeight:
                                    MediaQuery.sizeOf(context).height * 0.22,
                              ),
                              child: SingleChildScrollView(
                                child: Text(
                                  (showKo && cur.captionKo.trim().isNotEmpty)
                                      ? cite.stripCiteMarkersForDisplay(
                                          cur.captionKo,
                                        )
                                      : cite.stripCiteMarkersForDisplay(
                                          cur.caption,
                                        ),
                                  maxLines: captionFullText ? null : 2,
                                  overflow: captionFullText
                                      ? TextOverflow.visible
                                      : TextOverflow.ellipsis,
                                  softWrap: true,
                                  style:
                                      Theme.of(context).textTheme.bodySmall,
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

class _FigureInkStack extends StatefulWidget {
  const _FigureInkStack({
    required this.figureKey,
    required this.annotations,
    required this.child,
  });

  final String? figureKey;
  final AnnotationController annotations;
  final Widget child;

  @override
  State<_FigureInkStack> createState() => _FigureInkStackState();
}

class _FigureInkStackState extends State<_FigureInkStack> {
  List<Offset> _stroke = [];

  @override
  Widget build(BuildContext context) {
    final key = widget.figureKey;
    final inkEvents = widget.annotations.activeForFigureKey(key);
    return LayoutBuilder(
      builder: (context, constraints) {
        return Stack(
          fit: StackFit.expand,
          children: [
            widget.child,
            if (inkEvents.isNotEmpty)
              CustomPaint(
                painter: _InkPathsPainter(
                  events: inkEvents,
                  size: Size(constraints.maxWidth, constraints.maxHeight),
                ),
              ),
            if (widget.annotations.figureInkMode)
              GestureDetector(
                behavior: HitTestBehavior.translucent,
                onPanStart: (d) => _stroke = [d.localPosition],
                onPanUpdate: (d) => setState(() => _stroke.add(d.localPosition)),
                onPanEnd: (_) async {
                  if (key == null || _stroke.length < 2) {
                    setState(() => _stroke = []);
                    return;
                  }
                  final w = constraints.maxWidth;
                  final h = constraints.maxHeight;
                  if (w <= 0 || h <= 0) return;
                  final points = _stroke
                      .map((p) => [p.dx / w, p.dy / h])
                      .toList(growable: false);
                  await widget.annotations.addFigureInkPath(
                    figureKey: key,
                    points: points,
                  );
                  if (mounted) setState(() => _stroke = []);
                },
                child: CustomPaint(
                  painter: _LiveStrokePainter(_stroke),
                ),
              ),
          ],
        );
      },
    );
  }
}

class _InkPathsPainter extends CustomPainter {
  _InkPathsPainter({required this.events, required this.size});

  final List<AnnotationEvent> events;
  final Size size;

  @override
  void paint(Canvas canvas, Size canvasSize) {
    final paint = Paint()
      ..color = const Color(0xFFE53935)
      ..strokeWidth = 2
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;
    for (final ev in events) {
      for (final path in ev.paths) {
        final pts = path['points'];
        if (pts is! List || pts.length < 2) continue;
        final pathObj = Path();
        for (var i = 0; i < pts.length; i++) {
          final pt = pts[i];
          if (pt is! List || pt.length < 2) continue;
          final x = (pt[0] as num).toDouble() * canvasSize.width;
          final y = (pt[1] as num).toDouble() * canvasSize.height;
          if (i == 0) {
            pathObj.moveTo(x, y);
          } else {
            pathObj.lineTo(x, y);
          }
        }
        canvas.drawPath(pathObj, paint);
      }
    }
  }

  @override
  bool shouldRepaint(covariant _InkPathsPainter oldDelegate) =>
      oldDelegate.events != events || oldDelegate.size != size;
}

class _LiveStrokePainter extends CustomPainter {
  _LiveStrokePainter(this.points);
  final List<Offset> points;

  @override
  void paint(Canvas canvas, Size size) {
    if (points.length < 2) return;
    final paint = Paint()
      ..color = const Color(0xFFE53935)
      ..strokeWidth = 2
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;
    final path = Path()..moveTo(points.first.dx, points.first.dy);
    for (var i = 1; i < points.length; i++) {
      path.lineTo(points[i].dx, points[i].dy);
    }
    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(covariant _LiveStrokePainter oldDelegate) =>
      oldDelegate.points != points;
}

class _FigureImage extends StatelessWidget {
  const _FigureImage({
    required this.src,
    this.swipeEnabled = false,
    this.onPrevious,
    this.onNext,
    this.onTap,
    this.onDoubleTapExpand,
    this.onSwipeToSentence,
  });

  final String src;
  final bool swipeEnabled;
  final VoidCallback? onPrevious;
  final VoidCallback? onNext;
  final VoidCallback? onTap;
  final VoidCallback? onDoubleTapExpand;
  final VoidCallback? onSwipeToSentence;

  @override
  Widget build(BuildContext context) {
    if (src.isEmpty) {
      return GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        // design/124 — honest empty (product 3A); do not fake a successful image.
        child: const Center(child: Text('이미지 없음')),
      );
    }
    final decoded = decodeRasterDataUrl(src);
    if (decoded != null) {
      return _ZoomableFigureFrame(
        key: ValueKey<String>('fig-mem-${src.length}-${src.hashCode}'),
        swipeEnabled: swipeEnabled,
        onPrevious: onPrevious,
        onNext: onNext,
        onTap: onTap,
        onDoubleTapExpand: onDoubleTapExpand,
        onSwipeToSentence: onSwipeToSentence,
        child: Image.memory(
          decoded.bytes,
          fit: BoxFit.contain,
          filterQuality: FilterQuality.high,
        ),
      );
    }
    if (src.startsWith('http://') || src.startsWith('https://')) {
      return _ZoomableFigureFrame(
        key: ValueKey<String>('fig-net-${src.hashCode}'),
        swipeEnabled: swipeEnabled,
        onPrevious: onPrevious,
        onNext: onNext,
        onTap: onTap,
        onDoubleTapExpand: onDoubleTapExpand,
        onSwipeToSentence: onSwipeToSentence,
        child: Image.network(
          src,
          fit: BoxFit.contain,
          filterQuality: FilterQuality.high,
          errorBuilder: (_, __, ___) =>
              const Center(child: Text('이미지 없음')),
        ),
      );
    }
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: const Center(
        child: Padding(
          padding: EdgeInsets.all(12),
          child: Text(
            '이미지 없음 (이 형식은 미리보기 불가 · 캡션만)',
            textAlign: TextAlign.center,
          ),
        ),
      ),
    );
  }
}

/// design/95+143 — horizontal swipe: left→next, right→prev (figures only when not zoomed).
/// design/100 — single tap toggles chrome (deferred so double-tap expand wins).
class _SwipePager extends StatefulWidget {
  const _SwipePager({
    required this.child,
    required this.onPrevious,
    required this.onNext,
    this.onTap,
    this.onDoubleTap,
    this.onSwipeUp,
    this.enabled = true,
  });

  final Widget child;
  final Future<void> Function()? onPrevious;
  final Future<void> Function()? onNext;
  final VoidCallback? onTap;
  final VoidCallback? onDoubleTap;
  /// design/156 — sentence full-screen only: swipe up → figure panel.
  final VoidCallback? onSwipeUp;
  final bool enabled;

  @override
  State<_SwipePager> createState() => _SwipePagerState();
}

class _SwipePagerState extends State<_SwipePager> {
  static const double _minDistance = 56;
  static const double _minVelocity = 180;
  static const double _minVerticalDistance = 88;
  double _dx = 0;
  double _dy = 0;

  void _handleHorizontalDragEnd(DragEndDetails details) {
    if (!widget.enabled) return;
    final v = details.primaryVelocity ?? 0;
    // design/143 — gallery convention: finger left → next, right → previous.
    final goNext = _dx < -_minDistance || v < -_minVelocity;
    final goPrev = _dx > _minDistance || v > _minVelocity;
    _dx = 0;
    if (goPrev && widget.onPrevious != null) {
      widget.onPrevious!();
    } else if (goNext && widget.onNext != null) {
      widget.onNext!();
    }
  }

  void _handleVerticalDragEnd(DragEndDetails details) {
    if (!widget.enabled || widget.onSwipeUp == null) return;
    final v = details.primaryVelocity ?? 0;
    // design/156 — finger up → reveal figure full-screen.
    final goUp = _dy < -_minVerticalDistance || v < -_minVelocity;
    _dy = 0;
    if (goUp) {
      widget.onSwipeUp!();
    }
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: widget.onTap,
      onDoubleTap: widget.onDoubleTap,
      onHorizontalDragStart: widget.onSwipeUp == null
          ? (_) => _dx = 0
          : (_) {
              _dx = 0;
              _dy = 0;
            },
      onHorizontalDragUpdate: (d) => _dx += d.delta.dx,
      onHorizontalDragEnd: _handleHorizontalDragEnd,
      onVerticalDragStart: widget.onSwipeUp == null
          ? null
          : (_) {
              _dx = 0;
              _dy = 0;
            },
      onVerticalDragUpdate: widget.onSwipeUp == null
          ? null
          : (d) => _dy += d.delta.dy,
      onVerticalDragEnd:
          widget.onSwipeUp == null ? null : _handleVerticalDragEnd,
      child: widget.child,
    );
  }
}

/// design/94+95+97+100+116+117+118 — full-frame zoom; swipe at 1×; tap chrome; double-tap expand.
///
/// design/116 — do NOT put [onHorizontalDrag*] on a parent [GestureDetector]
/// around [InteractiveViewer]: that arena fight breaks pinch (esp. figure-only).
/// Keep full-surface tap/double-tap; detect 1× figure swipe from pan-at-identity.
///
/// design/117 — figure advance only when the gesture stayed **one-finger**.
/// Pinch (incl. scale back to 1× while fingers down) must not change index.
///
/// design/118 — amplify pinch scale so the same finger travel feels stronger.
class _ZoomableFigureFrame extends StatefulWidget {
  const _ZoomableFigureFrame({
    super.key,
    required this.child,
    this.swipeEnabled = false,
    this.onPrevious,
    this.onNext,
    this.onTap,
    this.onDoubleTapExpand,
    this.onSwipeToSentence,
  });

  final Widget child;
  final bool swipeEnabled;
  final VoidCallback? onPrevious;
  final VoidCallback? onNext;
  final VoidCallback? onTap;
  final VoidCallback? onDoubleTapExpand;
  /// design/156 — figure full-screen @ 1×: swipe down → sentence panel.
  final VoidCallback? onSwipeToSentence;

  @override
  State<_ZoomableFigureFrame> createState() => _ZoomableFigureFrameState();
}

class _ZoomableFigureFrameState extends State<_ZoomableFigureFrame> {
  final TransformationController _transform = TransformationController();
  static const double _minDistance = 56;
  static const double _minVerticalDistance = 88;
  static const double _minVelocity = 180;
  static const double _zoomEps = 1.02;
  static const double _maxScale = 8.0;
  Offset _panAtStart = Offset.zero;
  /// Peak [ScaleUpdateDetails.pointerCount] for the in-flight gesture.
  int _maxPointers = 0;
  /// Scale on axis at [onInteractionStart] — base for design/118 amplify.
  double _scaleAtGestureStart = 1.0;
  Offset _lastFocalPoint = Offset.zero;

  @override
  void dispose() {
    _transform.dispose();
    super.dispose();
  }

  void _onInteractionStart(ScaleStartDetails details) {
    // WHY: capture translation at gesture start for 1× horizontal swipe.
    final t = _transform.value.getTranslation();
    _panAtStart = Offset(t.x, t.y);
    _maxPointers = details.pointerCount;
    _scaleAtGestureStart = _transform.value.getMaxScaleOnAxis();
    _lastFocalPoint = details.localFocalPoint;
  }

  void _onInteractionUpdate(ScaleUpdateDetails details) {
    // WHY: pinch often starts as 1 pointer then becomes 2 — track the peak.
    if (details.pointerCount > _maxPointers) {
      _maxPointers = details.pointerCount;
    }
    final scaleNow = _transform.value.getMaxScaleOnAxis();
    // design/118+156 — amplify zoomed one-finger pan (IV is 1:1 by default).
    if (details.pointerCount == 1 && scaleNow > _zoomEps) {
      final delta = details.localFocalPoint - _lastFocalPoint;
      _lastFocalPoint = details.localFocalPoint;
      final extraX = amplifyFigurePanExtraDelta(delta: delta.dx);
      final extraY = amplifyFigurePanExtraDelta(delta: delta.dy);
      if (extraX.abs() > 1e-4 || extraY.abs() > 1e-4) {
        _transform.value = Matrix4.copy(_transform.value)
          ..translate(extraX, extraY);
      }
      return;
    }
    _lastFocalPoint = details.localFocalPoint;
    // design/118 — InteractiveViewer already applied 1:1 scale; strengthen it.
    // One-finger pan must stay untouched (117 swipe path).
    if (details.pointerCount < 2) return;
    final amplified = amplifyFigurePinchScale(rawScale: details.scale);
    final target =
        (_scaleAtGestureStart * amplified).clamp(1.0, _maxScale).toDouble();
    final current = _transform.value.getMaxScaleOnAxis();
    // EDGE: degenerate matrix — do not divide / explode.
    if (!current.isFinite || current < 1e-6) return;
    final factor = target / current;
    if (!factor.isFinite || (factor - 1.0).abs() < 1e-4) return;
    // Scale about the focal point so the figure does not jump sideways.
    final focalScene = _transform.toScene(details.localFocalPoint);
    final next = Matrix4.copy(_transform.value)
      ..translate(focalScene.dx, focalScene.dy)
      ..scale(factor)
      ..translate(-focalScene.dx, -focalScene.dy);
    _transform.value = next;
  }

  void _onInteractionEnd(ScaleEndDetails details) {
    if (!mounted) return;
    final scale = _transform.value.getMaxScaleOnAxis();
    final t = _transform.value.getTranslation();
    final dx = t.x - _panAtStart.dx;
    final dy = t.y - _panAtStart.dy;
    final maxPointers = _maxPointers;
    // Reset for the next gesture (after fingers up, one-finger swipe works again).
    _maxPointers = 0;

    // EDGE: pinch ended above 1× — keep pan/zoom; no figure change.
    if (scale > _zoomEps) {
      return;
    }

    // design/156 — vertical panel swap (before 1× snap-back).
    if (widget.onSwipeToSentence != null && maxPointers < 2) {
      final goDown = dy > _minVerticalDistance ||
          details.velocity.pixelsPerSecond.dy > _minVelocity;
      if (dy.abs() > dx.abs() && goDown) {
        _transform.value = Matrix4.identity();
        widget.onSwipeToSentence!();
        return;
      }
    }

    // WHY: 1× pan was only for swipe affordance — snap matrix back so the
    // figure does not sit offset after a failed/short drag / pinch-out.
    final needsSnap = (t.x.abs() > 0.5 ||
        t.y.abs() > 0.5 ||
        (scale - 1.0).abs() > 0.001);
    if (needsSnap) {
      _transform.value = Matrix4.identity();
    }

    if (!widget.swipeEnabled) return;
    // design/117 — never advance on multi-touch, even at 1×.
    if (!allowFigureSwipeAfterPan(
      maxPointerCount: maxPointers,
      scale: scale,
      zoomEps: _zoomEps,
    )) {
      return;
    }
    // Primary velocity is in logical px/s when available from scale end.
    // design/143 — gallery: finger left → next, right → previous.
    final v = details.velocity.pixelsPerSecond.dx;
    final goNext = dx < -_minDistance || v < -180;
    final goPrev = dx > _minDistance || v > 180;
    if (goPrev && widget.onPrevious != null) {
      widget.onPrevious!();
    } else if (goNext && widget.onNext != null) {
      widget.onNext!();
    }
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final w = constraints.maxWidth;
        final h = constraints.maxHeight;
        if (!w.isFinite || !h.isFinite || w <= 0 || h <= 0) {
          return widget.child;
        }
        // WHY: tap/double-tap only — no parent drag vs InteractiveViewer scale.
        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: widget.onTap,
          onDoubleTap: widget.onDoubleTapExpand,
          child: InteractiveViewer(
            transformationController: _transform,
            minScale: 1.0,
            maxScale: _maxScale,
            // WHY: pan at 1× enables swipe detection without HorizontalDrag.
            // Zoomed pan still moves the figure; 1× pan snaps back on end.
            panEnabled: true,
            scaleEnabled: true,
            boundaryMargin: const EdgeInsets.all(48),
            onInteractionStart: _onInteractionStart,
            onInteractionUpdate: _onInteractionUpdate,
            onInteractionEnd: _onInteractionEnd,
            child: SizedBox(
              width: w,
              height: h,
              child: ColoredBox(
                color: Colors.black,
                child: Center(child: widget.child),
              ),
            ),
          ),
        );
      },
    );
  }
}

Future<void> _handleSentenceBookmarkTap(
  BuildContext context, {
  required BookmarkController bookmarks,
  required ReadingSession session,
}) async {
  if (!bookmarks.canBookmark) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('북마크를 쓰려면 로그인해 주세요.')),
    );
    return;
  }
  final nav = session.sectionNav;
  final key = nav.sentenceBookmarkKeyForGlobal(session.sentenceIndex);
  if (bookmarks.isSentenceBookmarked(key)) {
    await bookmarks.toggleSentenceBookmark(nav, session.sentenceIndex);
    return;
  }
  final header = nav.headerPartsFor(session.sentenceIndex);
  final label = header.sectionName.isEmpty
      ? '${header.position}번 문장'
      : '${header.sectionName} ${header.position}번';
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('북마크할까요?'),
      content: Text(
        '$label을 북마크하면 쉽게 찾을 수 있어요.',
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
    await bookmarks.toggleSentenceBookmark(nav, session.sentenceIndex);
  }
}

Future<void> _handleSentenceAnnotateLongPress(
  BuildContext context, {
  required AnnotationController annotations,
  required ReadingSession session,
  required LibraryController library,
}) async {
  if (!annotations.canAnnotate) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('주석을 쓰려면 로그인해 주세요.')),
    );
    return;
  }
  final nav = session.sectionNav;
  final key = nav.sentenceBookmarkKeyForGlobal(session.sentenceIndex);
  if (key == null) return;
  final cur = session.currentSentence;
  if (cur == null) return;
  final existing = annotations.activeForSentenceKey(key);
  final result = await showAnnotationToolbarSheet(
    context: context,
    existing: existing,
  );
  if (result == null) return;
  if (result.delete) {
    await annotations.removeAnnotationsForKey(key);
    return;
  }
  final prefix = cur.text.length > 24 ? cur.text.substring(0, 12) : '';
  final suffix = cur.text.length > 24 ? cur.text.substring(cur.text.length - 12) : '';
  await annotations.upsertHighlight(
    sentenceKey: key,
    sentenceId: cur.id,
    color: result.color,
    note: result.note,
    existingId: result.existingId,
    selector: {
      'type': 'TextQuoteSelector',
      'exact': plainFromRichHtml(cur.text),
      if (prefix.isNotEmpty) 'prefix': prefix,
      if (suffix.isNotEmpty) 'suffix': suffix,
    },
  );
  HapticFeedback.mediumImpact();
}

Future<void> _handleFigureBookmarkTap(
  BuildContext context, {
  required BookmarkController bookmarks,
  required ReadingSession session,
}) async {
  if (!bookmarks.canBookmark) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('북마크를 쓰려면 로그인해 주세요.')),
    );
    return;
  }
  final nav = session.figureNav;
  final key = nav.figureBookmarkKeyForCarousel(session.figureIndex);
  if (bookmarks.isFigureBookmarked(key)) {
    await bookmarks.toggleFigureBookmark(nav, session.figureIndex);
    return;
  }
  final header = nav.headerPartsFor(
    session.figureIndex,
    totalFigures: session.figureCount,
  );
  final kind = header.kindLabel.isEmpty ? 'Figure' : header.kindLabel;
  final num = header.numberLabel.isEmpty ? '?' : header.numberLabel;
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('북마크할까요?'),
      content: Text(
        '$kind $num을 북마크하면 쉽게 찾을 수 있어요.',
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
    await bookmarks.toggleFigureBookmark(nav, session.figureIndex);
  }
}
