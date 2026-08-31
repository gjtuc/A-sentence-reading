import 'package:flutter/material.dart';

import '../api/annotation_models.dart';
import '../api/reader_nav_labels.dart';
import '../api/reading_models.dart';
import '../state/annotation_controller.dart';
import '../state/library_controller.dart';

/// Annotation list with color filter + jump (design/166 P1).
Future<void> showAnnotationListSheet({
  required BuildContext context,
  required ReadingSession session,
  required AnnotationController annotations,
  required LibraryController library,
}) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (ctx) => _AnnotationListBody(
      session: session,
      annotations: annotations,
      library: library,
    ),
  );
}

class _AnnotationListBody extends StatefulWidget {
  const _AnnotationListBody({
    required this.session,
    required this.annotations,
    required this.library,
  });

  final ReadingSession session;
  final AnnotationController annotations;
  final LibraryController library;

  @override
  State<_AnnotationListBody> createState() => _AnnotationListBodyState();
}

class _AnnotationListBodyState extends State<_AnnotationListBody> {
  String? _colorFilter;

  @override
  Widget build(BuildContext context) {
    final nav = widget.session.sectionNav;
    final rows = <_Row>[];
    for (final entry in widget.annotations.sentenceAnnotationEntries) {
      final key = entry.key;
      final global = nav.globalIndexForBookmarkKey(key);
      for (final ev in entry.value) {
        if (!ev.isActive) continue;
        if (_colorFilter != null && ev.color != _colorFilter) continue;
        rows.add(_Row(key: key, event: ev, globalIndex: global));
      }
    }
    rows.sort((a, b) => (a.globalIndex ?? 9999).compareTo(b.globalIndex ?? 9999));

    final maxH = MediaQuery.sizeOf(context).height * 0.7;
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 16),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Wrap(
            spacing: 8,
            children: [
              FilterChip(
                label: const Text('전체'),
                selected: _colorFilter == null,
                onSelected: (_) => setState(() => _colorFilter = null),
              ),
              for (final c in annotationColors)
                FilterChip(
                  label: Text(c),
                  selected: _colorFilter == c,
                  onSelected: (_) => setState(() => _colorFilter = c),
                ),
            ],
          ),
          const SizedBox(height: 8),
          ConstrainedBox(
            constraints: BoxConstraints(maxHeight: maxH),
            child: rows.isEmpty
                ? const Padding(
                    padding: EdgeInsets.all(24),
                    child: Text('주석이 없습니다.'),
                  )
                : ListView.separated(
                    shrinkWrap: true,
                    itemCount: rows.length,
                    separatorBuilder: (_, __) => const Divider(height: 1),
                    itemBuilder: (context, i) {
                      final row = rows[i];
                      final orphaned = row.event.status == 'orphaned';
                      final parts = row.key.split(':');
                      final label = parts.length == 2
                          ? '${parts[0]} · ${parts[1]}'
                          : row.key;
                      return ListTile(
                        leading: Container(
                          width: 16,
                          height: 16,
                          color: annotationColorValue(row.event.color),
                        ),
                        title: Text('$label${orphaned ? ' ⚠' : ''}'),
                        subtitle: row.event.note.isNotEmpty
                            ? Text(row.event.note, maxLines: 2)
                            : null,
                        onTap: row.globalIndex == null
                            ? null
                            : () async {
                                Navigator.pop(context);
                                await widget.library.goToSentenceIndex(row.globalIndex!);
                              },
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}

class _Row {
  const _Row({
    required this.key,
    required this.event,
    this.globalIndex,
  });

  final String key;
  final AnnotationEvent event;
  final int? globalIndex;
}
