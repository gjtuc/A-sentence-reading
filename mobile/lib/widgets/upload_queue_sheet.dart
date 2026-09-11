/// design/221 — bottom sheet listing reserved / active upload queue items.
library;

import 'package:flutter/material.dart';

import '../api/upload_reserve_models.dart';
import '../state/library_controller.dart';

Future<void> showUploadQueueSheet({
  required BuildContext context,
  required LibraryController library,
}) {
  return showModalBottomSheet<void>(
    context: context,
    showDragHandle: true,
    isScrollControlled: true,
    builder: (ctx) {
      return AnimatedBuilder(
        animation: library,
        builder: (context, _) {
          final items = library.uploadQueue;
          return SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    '업로드 대기 ${items.length}건',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '분석은 한 건씩 순서대로 진행됩니다. 대기 중 항목은 제거해도 됩니다.',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  const SizedBox(height: 12),
                  if (items.isEmpty)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 24),
                      child: Text('대기 중인 PDF가 없습니다.', textAlign: TextAlign.center),
                    )
                  else
                    ConstrainedBox(
                      constraints: BoxConstraints(
                        maxHeight: MediaQuery.sizeOf(context).height * 0.45,
                      ),
                      child: ListView.separated(
                        shrinkWrap: true,
                        itemCount: items.length,
                        separatorBuilder: (_, __) => const Divider(height: 1),
                        itemBuilder: (context, i) {
                          final item = items[i];
                          return _QueueTile(
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
                ],
              ),
            ),
          );
        },
      );
    },
  );
}

class _QueueTile extends StatelessWidget {
  const _QueueTile({required this.item, this.onRemove});

  final UploadReserveItem item;
  final VoidCallback? onRemove;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final label = item.isActive ? '분석 중' : '대기';
    return ListTile(
      contentPadding: EdgeInsets.zero,
      title: Text(
        item.filename,
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
      ),
      subtitle: Text(
        label,
        style: TextStyle(
          color: item.isActive ? scheme.primary : scheme.onSurfaceVariant,
        ),
      ),
      trailing: onRemove == null
          ? null
          : IconButton(
              tooltip: '대기 목록에서 제거',
              onPressed: onRemove,
              icon: const Icon(Icons.close),
            ),
    );
  }
}
