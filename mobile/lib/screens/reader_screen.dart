import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/reading_models.dart';
import '../api/rich_sentence.dart';
import '../state/library_controller.dart';
import '../state/shadowing_controller.dart';
import '../state/tts_controller.dart';
import 'shadowing_practice_screen.dart';

/// Split reader: sentence panel + figure panel (design/63) + TTS (design/64).
///
/// INVARIANT: sentence controls never call figure advance and vice versa.
/// TTS never mutates cursors.
class ReaderScreen extends StatelessWidget {
  const ReaderScreen({
    super.key,
    required this.library,
    required this.tts,
    required this.client,
    required this.shadowing,
  });

  final LibraryController library;
  final TtsController tts;
  final AsrClient client;
  final ShadowingController shadowing;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: Listenable.merge([library, tts]),
      builder: (context, _) {
        final s = library.session;
        if (s == null || !s.isValid) {
          return const Center(
            child: Padding(
              padding: EdgeInsets.all(24),
              child: Text(
                'No paper open. Open one from Library (sentence + figure + TTS).',
                textAlign: TextAlign.center,
              ),
            ),
          );
        }
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
              flex: 3,
              child: _SentencePanel(library: library, tts: tts, session: s),
            ),
            const Divider(height: 1),
            Expanded(flex: 2, child: _FigurePanel(library: library, session: s)),
          ],
        );
      },
    );
  }
}

class _SentencePanel extends StatelessWidget {
  const _SentencePanel({
    required this.library,
    required this.tts,
    required this.session,
  });

  final LibraryController library;
  final TtsController tts;
  final ReadingSession session;

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
          Row(
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
          ),
          if (tts.error != null)
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
                              if (cur.textKo.trim().isNotEmpty) ...[
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
          Row(
            children: [
              const Text('speed', style: TextStyle(fontSize: 12)),
              Expanded(
                child: Slider(
                  value: tts.rate.clamp(0.5, 2.2),
                  min: 0.5,
                  max: 2.2,
                  divisions: 17,
                  label: tts.rate.toStringAsFixed(2),
                  onChanged: (v) => tts.setRate(v),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _FigurePanel extends StatelessWidget {
  const _FigurePanel({required this.library, required this.session});

  final LibraryController library;
  final ReadingSession session;

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
          Row(
            children: [
              IconButton(
                tooltip: 'prev figure',
                onPressed: session.figureCount == 0
                    ? null
                    : () => library.advanceFigure(-1),
                icon: const Icon(Icons.chevron_left),
              ),
              Expanded(child: Text(label, textAlign: TextAlign.center)),
              IconButton(
                tooltip: 'next figure',
                onPressed: session.figureCount == 0
                    ? null
                    : () => library.advanceFigure(1),
                icon: const Icon(Icons.chevron_right),
              ),
            ],
          ),
          Expanded(
            child: Card(
              clipBehavior: Clip.antiAlias,
              child: cur == null
                  ? const Center(child: Text('No figure.'))
                  : Column(
                      children: [
                        Expanded(
                          child: _FigureImage(
                            src: cur.imageSrc,
                            swipeEnabled: session.figureCount > 0,
                            onPrevious: () => library.advanceFigure(-1),
                            onNext: () => library.advanceFigure(1),
                          ),
                        ),
                        if (cur.caption.trim().isNotEmpty ||
                            cur.captionKo.trim().isNotEmpty)
                          Padding(
                            padding: const EdgeInsets.all(8),
                            child: Text(
                              cur.captionKo.trim().isNotEmpty
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
  });

  final String src;
  final bool swipeEnabled;
  final VoidCallback? onPrevious;
  final VoidCallback? onNext;

  @override
  Widget build(BuildContext context) {
    if (src.isEmpty) {
      return const Center(child: Text('No image'));
    }
    final decoded = decodeRasterDataUrl(src);
    if (decoded != null) {
      return _ZoomableFigureFrame(
        key: ValueKey<String>('fig-mem-${src.length}-${src.hashCode}'),
        swipeEnabled: swipeEnabled,
        onPrevious: onPrevious,
        onNext: onNext,
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
        child: Image.network(
          src,
          fit: BoxFit.contain,
          filterQuality: FilterQuality.high,
          errorBuilder: (_, __, ___) =>
              const Center(child: Text('Image load failed')),
        ),
      );
    }
    return const Center(
      child: Padding(
        padding: EdgeInsets.all(12),
        child: Text(
          'Preview not available for this image type (caption only).',
          textAlign: TextAlign.center,
        ),
      ),
    );
  }
}

/// design/95 — horizontal swipe: left→prev, right→next (figures only when not zoomed).
class _SwipePager extends StatefulWidget {
  const _SwipePager({
    required this.child,
    required this.onPrevious,
    required this.onNext,
    this.enabled = true,
  });

  final Widget child;
  final Future<void> Function()? onPrevious;
  final Future<void> Function()? onNext;
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
      onHorizontalDragStart: (_) => _dx = 0,
      onHorizontalDragUpdate: (d) => _dx += d.delta.dx,
      onHorizontalDragEnd: _handleDragEnd,
      child: widget.child,
    );
  }
}

/// design/94+95 — full-frame zoom; swipe nav only at scale ≈ 1.
class _ZoomableFigureFrame extends StatefulWidget {
  const _ZoomableFigureFrame({
    super.key,
    required this.child,
    this.swipeEnabled = false,
    this.onPrevious,
    this.onNext,
  });

  final Widget child;
  final bool swipeEnabled;
  final VoidCallback? onPrevious;
  final VoidCallback? onNext;

  @override
  State<_ZoomableFigureFrame> createState() => _ZoomableFigureFrameState();
}

class _ZoomableFigureFrameState extends State<_ZoomableFigureFrame> {
  final TransformationController _transform = TransformationController();
  static const double _minDistance = 56;
  static const double _minVelocity = 180;
  double _dx = 0;

  bool get _zoomed {
    final s = _transform.value.getMaxScaleOnAxis();
    return s > 1.02;
  }

  @override
  void dispose() {
    _transform.dispose();
    super.dispose();
  }

  void _onSwipeEnd(DragEndDetails details) {
    if (!widget.swipeEnabled || _zoomed) return;
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
    return LayoutBuilder(
      builder: (context, constraints) {
        final w = constraints.maxWidth;
        final h = constraints.maxHeight;
        if (!w.isFinite || !h.isFinite || w <= 0 || h <= 0) {
          return widget.child;
        }
        final allowSwipe = widget.swipeEnabled && !_zoomed;
        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onHorizontalDragStart: allowSwipe ? (_) => _dx = 0 : null,
          onHorizontalDragUpdate:
              allowSwipe ? (d) => _dx += d.delta.dx : null,
          onHorizontalDragEnd: allowSwipe ? _onSwipeEnd : null,
          child: InteractiveViewer(
            transformationController: _transform,
            minScale: 1.0,
            maxScale: 8.0,
            // WHY: at 1×, disable pan so horizontal swipe can change figures.
            panEnabled: _zoomed,
            boundaryMargin: const EdgeInsets.all(48),
            onInteractionUpdate: (_) {
              if (mounted) setState(() {});
            },
            onInteractionEnd: (_) {
              if (mounted) setState(() {});
            },
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
