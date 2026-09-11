/// Shared upload / reanalyze progress chrome (design/225-U).
library;

import 'package:flutter/material.dart';

import '../state/library_controller.dart';
import 'upload_queue_sheet.dart';

/// Compact status bar for library sliver or reader column.
class UploadStatusBar extends StatelessWidget {
  const UploadStatusBar({
    super.key,
    required this.library,
    this.onResume,
    this.padding = const EdgeInsets.fromLTRB(16, 0, 16, 8),
    this.dense = false,
  });

  final LibraryController library;
  final VoidCallback? onResume;
  final EdgeInsetsGeometry padding;
  final bool dense;

  bool get _visible =>
      library.reanalyzing ||
      library.uploading ||
      library.uploadStalled ||
      library.uploadQueue.isNotEmpty;

  @override
  Widget build(BuildContext context) {
    if (!_visible) return const SizedBox.shrink();
    final lib = library;
    final theme = Theme.of(context);

    if (lib.reanalyzing) {
      return Padding(
        padding: padding,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            LinearProgressIndicator(
              value: lib.uploadPercent > 0
                  ? (lib.uploadPercent.clamp(0, 100) / 100.0)
                  : null,
            ),
            SizedBox(height: dense ? 4 : 6),
            Text(
              '재분석 중 ${lib.uploadPercent}%'
              '${lib.uploadStage.isEmpty ? '' : ' · ${lib.uploadStage}'}',
              style: theme.textTheme.bodySmall,
            ),
          ],
        ),
      );
    }

    if (!lib.uploading && lib.uploadQueue.isEmpty) {
      return const SizedBox.shrink();
    }

    return Padding(
      padding: padding,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (lib.uploading)
            LinearProgressIndicator(
              // EDGE (design/75): stalled → do not animate fake progress.
              value: lib.uploadStalled
                  ? 0
                  : (lib.uploadPercent > 0
                      ? (lib.uploadPercent.clamp(0, 100) / 100.0)
                      : null),
            ),
          if (lib.uploading) SizedBox(height: dense ? 4 : 6),
          Text(
            lib.uploadStalled
                ? (lib.uploadStage.isEmpty
                    ? '중단됨 · 앱을 열면 이어갑니다'
                    : lib.uploadStage)
                : lib.uploading
                    ? (
                        // design/185 — device SoT; analysis then save on this phone.
                        '처리 중 ${lib.uploadPercent}%'
                        '${lib.uploadStage.isEmpty ? '' : ' · ${lib.uploadStage}'}'
                        ' · 끝나면 이 기기에 저장'
                        '${lib.uploadQueue.length > 1 ? ' · 대기 ${lib.uploadQueue.length - 1}' : ''}'
                      )
                    : '업로드 대기 ${lib.uploadQueue.length}건',
            style: theme.textTheme.bodySmall,
          ),
          SizedBox(height: dense ? 4 : 8),
          Wrap(
            spacing: 4,
            runSpacing: 0,
            children: [
              if (lib.uploadStalled && onResume != null)
                TextButton(
                  onPressed: lib.opening || lib.reanalyzing ? null : onResume,
                  child: const Text('지금 이어가기'),
                ),
              if (lib.uploading)
                TextButton(
                  // design/132 — early cancel; late stage may refuse on server.
                  onPressed: () => lib.cancelUpload(),
                  child: const Text('취소'),
                ),
              if (lib.uploadQueue.isNotEmpty)
                TextButton(
                  onPressed: () => showUploadQueueSheet(
                    context: context,
                    library: lib,
                  ),
                  child: const Text('대기열'),
                ),
            ],
          ),
          if (lib.uploadBatteryHint != null) ...[
            SizedBox(height: dense ? 4 : 8),
            Text(
              lib.uploadBatteryHint!,
              style: theme.textTheme.bodySmall,
            ),
            const SizedBox(height: 4),
            Wrap(
              spacing: 8,
              children: [
                TextButton(
                  onPressed: () async {
                    await lib.openBatterySettings();
                  },
                  child: const Text('배터리 제한 해제'),
                ),
                TextButton(
                  onPressed: () => lib.dismissBatteryHint(),
                  child: const Text('나중에'),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}
