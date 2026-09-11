/// design/223 — custom upload sheet: recent (green if in library) + queue + SAF.
library;

import 'package:flutter/material.dart';

import '../api/upload_picker_recent_models.dart';
import '../api/upload_reserve_models.dart';
import '../state/library_controller.dart';

Future<void> showUploadPickerSheet({
  required BuildContext context,
  required LibraryController library,
  required Future<void> Function() onPickFromFiles,
}) {
  asrEvidenceOpen(library);
  return showModalBottomSheet<void>(
    context: context,
    showDragHandle: true,
    isScrollControlled: true,
    builder: (ctx) {
      return AnimatedBuilder(
        animation: library,
        builder: (context, _) {
          final recent = library.pickerRecent;
          final queue = library.uploadQueue;
          final inLib = library.libraryContentHashes;
          final queued = {
            for (final q in queue) q.contentHash,
          };
          return SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
              child: ConstrainedBox(
                constraints: BoxConstraints(
                  maxHeight: MediaQuery.sizeOf(context).height * 0.72,
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      'PDF 가져오기',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '초록 테두리 = 이미 보관함에 있는 파일(내용 기준). 연결/병합과는 다릅니다.',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                    const SizedBox(height: 12),
                    FilledButton.icon(
                      onPressed: library.reanalyzing || library.opening
                          ? null
                          : () async {
                              Navigator.of(context).pop();
                              await onPickFromFiles();
                            },
                      icon: const Icon(Icons.folder_open),
                      label: const Text('파일에서 추가'),
                    ),
                    const SizedBox(height: 16),
                    Text(
                      '대기열 ${queue.length}',
                      style: Theme.of(context).textTheme.titleSmall,
                    ),
                    if (queue.isEmpty)
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        child: Text(
                          '대기 중인 업로드 없음',
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      )
                    else
                      Flexible(
                        child: ListView.separated(
                          shrinkWrap: true,
                          itemCount: queue.length,
                          separatorBuilder: (_, __) => const Divider(height: 1),
                          itemBuilder: (context, i) {
                            final item = queue[i];
                            return _QueueRow(
                              item: item,
                              onRemove: item.isActive
                                  ? null
                                  : () => library.removeUploadQueueItem(
                                        item.contentHash,
                                      ),
                            );
                          },
                        ),
                      ),
                    const SizedBox(height: 12),
                    Text(
                      '최근 ${recent.length}',
                      style: Theme.of(context).textTheme.titleSmall,
                    ),
                    if (recent.isEmpty)
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        child: Text(
                          '아직 최근 기록이 없습니다.',
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      )
                    else
                      Flexible(
                        child: ListView.separated(
                          shrinkWrap: true,
                          itemCount: recent.length,
                          separatorBuilder: (_, __) => const Divider(height: 1),
                          itemBuilder: (context, i) {
                            final item = recent[i];
                            final green = inLib.contains(item.contentHash);
                            final inQ = queued.contains(item.contentHash);
                            return _RecentRow(
                              item: item,
                              inLibrary: green,
                              inQueue: inQ,
                              onTap: () {
                                final msg = green
                                    ? '이미 보관함에 있습니다. (내용 동일)'
                                    : (inQ
                                        ? '이미 업로드 대기열에 있습니다.'
                                        : '같은 파일을 다시 고르려면 「파일에서 추가」를 사용하세요.');
                                ScaffoldMessenger.of(context).showSnackBar(
                                  SnackBar(content: Text(msg)),
                                );
                              },
                            );
                          },
                        ),
                      ),
                  ],
                ),
              ),
            ),
          );
        },
      );
    },
  );
}

void asrEvidenceOpen(LibraryController library) {
  // Lightweight breadcrumb; library records via controller helper.
  library.notePickerSheetOpened();
}

class _QueueRow extends StatelessWidget {
  const _QueueRow({required this.item, this.onRemove});

  final UploadReserveItem item;
  final VoidCallback? onRemove;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      contentPadding: EdgeInsets.zero,
      title: Text(item.filename, maxLines: 2, overflow: TextOverflow.ellipsis),
      subtitle: Text(item.isActive ? '분석 중' : '대기'),
      trailing: onRemove == null
          ? null
          : IconButton(
              tooltip: '대기 제거',
              onPressed: onRemove,
              icon: const Icon(Icons.close),
            ),
    );
  }
}

class _RecentRow extends StatelessWidget {
  const _RecentRow({
    required this.item,
    required this.inLibrary,
    required this.inQueue,
    required this.onTap,
  });

  final PickerRecentItem item;
  final bool inLibrary;
  final bool inQueue;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final border = inLibrary
        ? Border.all(color: Colors.green.shade600, width: 2)
        : Border.all(color: scheme.outlineVariant);
    final when = item.uploadedAtMs > 0
        ? DateTime.fromMillisecondsSinceEpoch(item.uploadedAtMs).toLocal()
        : null;
    final whenLabel = when == null
        ? ''
        : '${when.month}/${when.day} '
            '${when.hour.toString().padLeft(2, '0')}:'
            '${when.minute.toString().padLeft(2, '0')}';
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Material(
        color: scheme.surface,
        child: InkWell(
          onTap: onTap,
          child: Container(
            decoration: BoxDecoration(
              border: border,
              borderRadius: BorderRadius.circular(8),
            ),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  item.displayName,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
                const SizedBox(height: 4),
                Text(
                  [
                    if (inLibrary) '이미 보관',
                    if (inQueue) '대기열',
                    if (whenLabel.isNotEmpty) whenLabel,
                    if (item.label.isNotEmpty) item.label,
                  ].where((s) => s.isNotEmpty).join(' · '),
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: inLibrary
                            ? Colors.green.shade700
                            : scheme.onSurfaceVariant,
                      ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
