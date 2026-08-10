import 'package:flutter/material.dart';

import '../api/reading_models.dart';
import '../state/library_controller.dart';
import '../state/tts_controller.dart';

/// Split reader: sentence panel + figure panel (design/63) + TTS (design/64).
///
/// INVARIANT: sentence controls never call figure advance and vice versa.
/// TTS never mutates cursors (Live Enable / IPS: ASR out).
class ReaderScreen extends StatelessWidget {
  const ReaderScreen({super.key, required this.library, required this.tts});

  final LibraryController library;
  final TtsController tts;

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
                'No paper open. Open one from Library (sentence + figure + TTS). Live Enable/IPS: ASR out.',
                textAlign: TextAlign.center,
              ),
            ),
          );
        }
        return Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
              child: Text(
                s.title.isEmpty ? '(no title)' : s.title,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.titleSmall,
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
            const Padding(
              padding: EdgeInsets.only(bottom: 6),
              child: Text(
                'Live Enable / IPS: Trading Gate (ASR out)',
                style: TextStyle(fontSize: 11),
              ),
            ),
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
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: SingleChildScrollView(
                  child: cur == null || !cur.hasText
                      ? const Text('No sentence at this index.')
                      : Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              cur.text,
                              style: Theme.of(context).textTheme.titleMedium,
                            ),
                            if (cur.textKo.trim().isNotEmpty) ...[
                              const SizedBox(height: 12),
                              Text(
                                cur.textKo,
                                style: Theme.of(context).textTheme.bodyMedium,
                              ),
                            ],
                          ],
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
                        Expanded(child: _FigureImage(src: cur.imageSrc)),
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
  const _FigureImage({required this.src});

  final String src;

  @override
  Widget build(BuildContext context) {
    if (src.isEmpty) {
      return const Center(child: Text('No image'));
    }
    final decoded = decodeRasterDataUrl(src);
    if (decoded != null) {
      return InteractiveViewer(
        child: Image.memory(decoded.bytes, fit: BoxFit.contain),
      );
    }
    if (src.startsWith('http://') || src.startsWith('https://')) {
      return InteractiveViewer(
        child: Image.network(
          src,
          fit: BoxFit.contain,
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
