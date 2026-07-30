import 'package:flutter/material.dart';

import '../api/reading_models.dart';
import '../state/library_controller.dart';

/// Split reader: sentence panel + figure panel (design/63).
///
/// INVARIANT: sentence controls never call figure advance and vice versa.
class ReaderScreen extends StatelessWidget {
  const ReaderScreen({super.key, required this.library});

  final LibraryController library;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: library,
      builder: (context, _) {
        final s = library.session;
        if (s == null || !s.isValid) {
          return const Center(
            child: Padding(
              padding: EdgeInsets.all(24),
              child: Text(
                'No paper open. Open one from Library (sentence + figure). TTS next. Live Enable/IPS: ASR out.',
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
            Expanded(flex: 3, child: _SentencePanel(library: library, session: s)),
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
  const _SentencePanel({required this.library, required this.session});

  final LibraryController library;
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
                    : () => library.advanceSentence(-1),
                icon: const Icon(Icons.chevron_left),
              ),
              Expanded(child: Text(label, textAlign: TextAlign.center)),
              IconButton(
                tooltip: 'next sentence',
                onPressed: session.sentenceCount == 0
                    ? null
                    : () => library.advanceSentence(1),
                icon: const Icon(Icons.chevron_right),
              ),
            ],
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
