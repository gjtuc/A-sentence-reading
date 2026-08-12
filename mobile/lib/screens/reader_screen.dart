import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/reading_models.dart';
import '../api/rich_sentence.dart';
import '../state/library_controller.dart';
import '../state/shadowing_controller.dart';
import '../state/translate_controller.dart';
import '../state/tts_controller.dart';
import 'shadowing_practice_screen.dart';

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
  });

  final LibraryController library;
  final TtsController tts;
  final AsrClient client;
  final ShadowingController shadowing;
  final TranslateController translate;

  @override
  State<ReaderScreen> createState() => _ReaderScreenState();
}

class _ReaderScreenState extends State<ReaderScreen> {
  static const double _kDefaultFraction = 0.6;
  static const double _kMagnetEps = 0.028;
  static const double _kEdgeSnap = 0.14;
  static const double _kHardMin = 0.02;
  static const double _kHardMax = 0.98;
  static const double _kSplitBar = 16;

  _ReaderLayoutMode _layout = _ReaderLayoutMode.split;
  double _sentenceFraction = _kDefaultFraction;
  bool _dragging = false;
  bool _inMagnet = false;
  bool _edgePreviewSentence = false;
  bool _edgePreviewFigure = false;
  /// design/100 — shared chrome for sentence + figure headers.
  bool _chromeVisible = true;
  /// design/114 — reset split when a different paper is opened.
  String? _layoutSessionKey;

  void _ensureLayoutForSession(ReadingSession s) {
    final key = '${s.sessionId}|${s.cacheId}';
    if (_layoutSessionKey == key) return;
    _layoutSessionKey = key;
    _layout = _ReaderLayoutMode.split;
    _sentenceFraction = _kDefaultFraction;
    _chromeVisible = true;
    _dragging = false;
    _inMagnet = false;
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

  void _onSplitDragUpdate(double deltaDy, double totalH) {
    if (totalH <= _kSplitBar + 1) return;
    final usable = totalH - _kSplitBar;
    setState(() {
      _dragging = true;
      _layout = _ReaderLayoutMode.split;
      // Edge tension: drag moves slower near full-panel snap zones.
      final nearEdge = _sentenceFraction < _kEdgeSnap ||
          _sentenceFraction > 1 - _kEdgeSnap;
      final scale = nearEdge ? 0.32 : 1.0;
      var next =
          (_sentenceFraction + (deltaDy / usable) * scale).clamp(_kHardMin, _kHardMax);
      // Magnetic soft pull toward default while inside band.
      if ((next - _kDefaultFraction).abs() <= _kMagnetEps) {
        if (!_inMagnet) {
          _inMagnet = true;
          Feedback.forTap(context);
        }
        next = _kDefaultFraction;
      } else {
        _inMagnet = false;
      }
      _sentenceFraction = next;
      _edgePreviewSentence = next >= 1 - _kEdgeSnap;
      _edgePreviewFigure = next <= _kEdgeSnap;
    });
  }

  void _onSplitDragEnd() {
    setState(() {
      _dragging = false;
      if (_sentenceFraction >= 1 - _kEdgeSnap) {
        _layout = _ReaderLayoutMode.sentenceOnly;
        _sentenceFraction = _kDefaultFraction;
      } else if (_sentenceFraction <= _kEdgeSnap) {
        _layout = _ReaderLayoutMode.figureOnly;
        _sentenceFraction = _kDefaultFraction;
      } else if ((_sentenceFraction - _kDefaultFraction).abs() <= _kMagnetEps) {
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
      animation: Listenable.merge([library, tts, translate]),
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
                  // design/82 — separate practice mode (gated by kill + opt-in).
                  TextButton(
                    onPressed: (!shadowing.serverAvailable || !shadowing.enabled)
                        ? null
                        : () {
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
                                      session: s,
                                      showKo: showKo,
                                      showChrome: _chromeVisible,
                                      onToggleChrome: _toggleChrome,
                                      onDoubleTapExpand: _toggleSentenceExpand,
                                    ),
                            ),
                          ),
                          if (showBar)
                            _SplitHandle(
                              height: _kSplitBar,
                              magnetActive: _inMagnet,
                              edgePreviewSentence: _edgePreviewSentence,
                              edgePreviewFigure: _edgePreviewFigure,
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
                                      session: s,
                                      showKo: showKo,
                                      showChrome: _chromeVisible,
                                      onToggleChrome: _toggleChrome,
                                      onDoubleTapExpand: _toggleFigureExpand,
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
    required this.onDragUpdate,
    required this.onDragEnd,
    this.magnetActive = false,
    this.edgePreviewSentence = false,
    this.edgePreviewFigure = false,
  });

  final double height;
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
    required this.session,
    required this.showKo,
    required this.showChrome,
    this.onToggleChrome,
    this.onDoubleTapExpand,
  });

  final LibraryController library;
  final TtsController tts;
  final ReadingSession session;
  final bool showKo;
  final bool showChrome;
  final VoidCallback? onToggleChrome;
  final VoidCallback? onDoubleTapExpand;

  @override
  Widget build(BuildContext context) {
    final cur = session.currentSentence;
    final label = session.sentenceCount == 0
        ? 'no sentences'
        : 'sentence ${session.sentenceIndex + 1} / ${session.sentenceCount}';
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
                      Expanded(child: Text(label, textAlign: TextAlign.center)),
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
                // design/95 — swipe left → prev, swipe right → next
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
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: SingleChildScrollView(
                    child: cur == null || !cur.hasText
                        ? const Text('No sentence at this index.')
                        : Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              // design/88 — allowlisted <sub>/<sup>/<i> (not raw tags).
                              richSentenceText(
                                cur.text,
                                style: Theme.of(context).textTheme.titleMedium ??
                                    const TextStyle(fontSize: 18),
                              ),
                              if (showKo && cur.textKo.trim().isNotEmpty) ...[
                                const SizedBox(height: 12),
                                richSentenceText(
                                  cur.textKo,
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
        ],
      ),
    );
  }
}

class _FigurePanel extends StatelessWidget {
  const _FigurePanel({
    required this.library,
    required this.session,
    required this.showKo,
    required this.showChrome,
    this.onToggleChrome,
    this.onDoubleTapExpand,
  });

  final LibraryController library;
  final ReadingSession session;
  final bool showKo;
  final bool showChrome;
  final VoidCallback? onToggleChrome;
  final VoidCallback? onDoubleTapExpand;

  @override
  Widget build(BuildContext context) {
    final cur = session.currentFigure;
    final label = session.figureCount == 0
        ? 'no figures'
        : 'figure ${session.figureIndex + 1} / ${session.figureCount}';
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
                        child: Text(label, textAlign: TextAlign.center),
                      ),
                      IconButton(
                        tooltip: 'next figure',
                        onPressed: session.figureCount == 0
                            ? null
                            : () => library.advanceFigure(1),
                        icon: const Icon(Icons.chevron_right),
                      ),
                    ],
                  )
                : const SizedBox(width: double.infinity),
          ),
          Expanded(
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
                          child: _FigureImage(
                            src: cur.imageSrc,
                            swipeEnabled: session.figureCount > 0,
                            onPrevious: () => library.advanceFigure(-1),
                            onNext: () => library.advanceFigure(1),
                            onTap: onToggleChrome,
                            onDoubleTapExpand: onDoubleTapExpand,
                          ),
                        ),
                        if (cur.caption.trim().isNotEmpty ||
                            (showKo && cur.captionKo.trim().isNotEmpty))
                          Padding(
                            padding: const EdgeInsets.all(8),
                            child: Text(
                              (showKo && cur.captionKo.trim().isNotEmpty)
                                  ? cur.captionKo
                                  : cur.caption,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: Theme.of(context).textTheme.bodySmall,
                            ),
                          ),
                      ],
                    ),
            ),
          ),
        ],
      ),
    );
  }
}

class _FigureImage extends StatelessWidget {
  const _FigureImage({
    required this.src,
    this.swipeEnabled = false,
    this.onPrevious,
    this.onNext,
    this.onTap,
    this.onDoubleTapExpand,
  });

  final String src;
  final bool swipeEnabled;
  final VoidCallback? onPrevious;
  final VoidCallback? onNext;
  final VoidCallback? onTap;
  final VoidCallback? onDoubleTapExpand;

  @override
  Widget build(BuildContext context) {
    if (src.isEmpty) {
      return GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: const Center(child: Text('No image')),
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
        child: Image.network(
          src,
          fit: BoxFit.contain,
          filterQuality: FilterQuality.high,
          errorBuilder: (_, __, ___) =>
              const Center(child: Text('Image load failed')),
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
            'Preview not available for this image type (caption only).',
            textAlign: TextAlign.center,
          ),
        ),
      ),
    );
  }
}

/// design/95 — horizontal swipe: left→prev, right→next (figures only when not zoomed).
/// design/100 — single tap toggles chrome (deferred so double-tap expand wins).
class _SwipePager extends StatefulWidget {
  const _SwipePager({
    required this.child,
    required this.onPrevious,
    required this.onNext,
    this.onTap,
    this.onDoubleTap,
    this.enabled = true,
  });

  final Widget child;
  final Future<void> Function()? onPrevious;
  final Future<void> Function()? onNext;
  final VoidCallback? onTap;
  final VoidCallback? onDoubleTap;
  final bool enabled;

  @override
  State<_SwipePager> createState() => _SwipePagerState();
}

class _SwipePagerState extends State<_SwipePager> {
  static const double _minDistance = 56;
  static const double _minVelocity = 180;
  double _dx = 0;

  void _handleDragEnd(DragEndDetails details) {
    if (!widget.enabled) return;
    final v = details.primaryVelocity ?? 0;
    final goPrev = _dx < -_minDistance || v < -_minVelocity;
    final goNext = _dx > _minDistance || v > _minVelocity;
    _dx = 0;
    if (goPrev && widget.onPrevious != null) {
      widget.onPrevious!();
    } else if (goNext && widget.onNext != null) {
      widget.onNext!();
    }
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: widget.onTap,
      onDoubleTap: widget.onDoubleTap,
      onHorizontalDragStart: (_) => _dx = 0,
      onHorizontalDragUpdate: (d) => _dx += d.delta.dx,
      onHorizontalDragEnd: _handleDragEnd,
      child: widget.child,
    );
  }
}

/// design/94+95+97+100+116 — full-frame zoom; swipe at 1×; tap chrome; double-tap expand.
///
/// design/116 — do NOT put [onHorizontalDrag*] on a parent [GestureDetector]
/// around [InteractiveViewer]: that arena fight breaks pinch (esp. figure-only).
/// Keep full-surface tap/double-tap; detect 1× figure swipe from pan-at-identity.
class _ZoomableFigureFrame extends StatefulWidget {
  const _ZoomableFigureFrame({
    super.key,
    required this.child,
    this.swipeEnabled = false,
    this.onPrevious,
    this.onNext,
    this.onTap,
    this.onDoubleTapExpand,
  });

  final Widget child;
  final bool swipeEnabled;
  final VoidCallback? onPrevious;
  final VoidCallback? onNext;
  final VoidCallback? onTap;
  final VoidCallback? onDoubleTapExpand;

  @override
  State<_ZoomableFigureFrame> createState() => _ZoomableFigureFrameState();
}

class _ZoomableFigureFrameState extends State<_ZoomableFigureFrame> {
  final TransformationController _transform = TransformationController();
  static const double _minDistance = 56;
  static const double _zoomEps = 1.02;
  Offset _panAtStart = Offset.zero;

  @override
  void dispose() {
    _transform.dispose();
    super.dispose();
  }

  void _onInteractionStart(ScaleStartDetails details) {
    // WHY: capture translation at gesture start for 1× horizontal swipe.
    final t = _transform.value.getTranslation();
    _panAtStart = Offset(t.x, t.y);
  }

  void _onInteractionEnd(ScaleEndDetails details) {
    if (!mounted) return;
    final scale = _transform.value.getMaxScaleOnAxis();
    final t = _transform.value.getTranslation();
    final dx = t.x - _panAtStart.dx;

    // EDGE: pinch ended above 1× — keep pan/zoom; no figure change.
    if (scale > _zoomEps) {
      return;
    }

    // WHY: 1× pan was only for swipe affordance — snap matrix back so the
    // figure does not sit offset after a failed/short drag.
    final needsSnap = (t.x.abs() > 0.5 ||
        t.y.abs() > 0.5 ||
        (scale - 1.0).abs() > 0.001);
    if (needsSnap) {
      _transform.value = Matrix4.identity();
    }

    if (!widget.swipeEnabled) return;
    // Primary velocity is in logical px/s when available from scale end.
    final v = details.velocity.pixelsPerSecond.dx;
    final goPrev = dx < -_minDistance || v < -180;
    final goNext = dx > _minDistance || v > 180;
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
            maxScale: 8.0,
            // WHY: pan at 1× enables swipe detection without HorizontalDrag.
            // Zoomed pan still moves the figure; 1× pan snaps back on end.
            panEnabled: true,
            scaleEnabled: true,
            boundaryMargin: const EdgeInsets.all(48),
            onInteractionStart: _onInteractionStart,
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
