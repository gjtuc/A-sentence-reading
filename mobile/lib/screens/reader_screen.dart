import 'package:flutter/material.dart';

import '../state/library_controller.dart';

/// Reader placeholder — shows opened session until full reader (design/33 next).
///
/// Invariant reminder: sentence index is independent of figure index (PRODUCT).
class ReaderScreen extends StatelessWidget {
  const ReaderScreen({super.key, required this.library});

  final LibraryController library;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: library,
      builder: (context, _) {
        final o = library.opened;
        if (o == null || !o.isValid) {
          return const Center(
            child: Padding(
              padding: EdgeInsets.all(24),
              child: Text(
                '읽기\n\n'
                '보관에서 논문을 열면 여기에 세션이 표시됩니다.\n'
                '문장·그림 패널과 TTS는 다음 단계에서 붙입니다.\n'
                'AI 채점·Live Enable·IPS는 이 앱 범위가 아닙니다.',
                textAlign: TextAlign.center,
              ),
            ),
          );
        }
        return ListView(
          padding: const EdgeInsets.all(24),
          children: [
            Text('세션 열림', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 12),
            Text(o.title.isEmpty ? '(제목 없음)' : o.title),
            const SizedBox(height: 8),
            Text(
              'session: ${o.sessionId}',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            Text(
              'cache: ${o.cacheId}',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            Text('문장 ${o.sentenceCount} · 그림 ${o.figureCount}'),
            if (o.warnings.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text('경고: ${o.warnings.join(', ')}'),
            ],
            const SizedBox(height: 24),
            const Text(
              '다음 검토: 문장 하나 · 그림 하나 · 인덱스 독립 이동.\n'
              'Live Enable / IPS: Trading Gate · ASR 밖.',
            ),
          ],
        );
      },
    );
  }
}
