import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/annotation_models.dart';

/// Bottom sheet for highlight color + optional note (design/166).
Future<AnnotationToolbarResult?> showAnnotationToolbarSheet({
  required BuildContext context,
  List<AnnotationEvent> existing = const [],
}) {
  return showModalBottomSheet<AnnotationToolbarResult>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (ctx) {
      return _AnnotationToolbarBody(existing: existing);
    },
  );
}

class AnnotationToolbarResult {
  const AnnotationToolbarResult({
    required this.color,
    this.note = '',
    this.delete = false,
    this.existingId,
  });

  final String color;
  final String note;
  final bool delete;
  final String? existingId;
}

class _AnnotationToolbarBody extends StatefulWidget {
  const _AnnotationToolbarBody({this.existing = const []});

  final List<AnnotationEvent> existing;

  @override
  State<_AnnotationToolbarBody> createState() => _AnnotationToolbarBodyState();
}

class _AnnotationToolbarBodyState extends State<_AnnotationToolbarBody> {
  late String _color;
  late final TextEditingController _noteCtrl;
  String? _existingId;

  @override
  void initState() {
    super.initState();
    final first = widget.existing.isNotEmpty ? widget.existing.first : null;
    _color = first?.color ?? 'yellow';
    _existingId = first?.id;
    _noteCtrl = TextEditingController(text: first?.note ?? '');
  }

  @override
  void dispose() {
    _noteCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(
        16,
        8,
        16,
        16 + MediaQuery.viewInsetsOf(context).bottom,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: [
              for (final c in annotationColors)
                GestureDetector(
                  onTap: () => setState(() => _color = c),
                  child: Container(
                    width: 40,
                    height: 40,
                    decoration: BoxDecoration(
                      color: annotationColorValue(c),
                      shape: BoxShape.circle,
                      border: _color == c
                          ? Border.all(color: Theme.of(context).colorScheme.primary, width: 2)
                          : null,
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _noteCtrl,
            decoration: const InputDecoration(
              labelText: '메모 (선택)',
              border: OutlineInputBorder(),
            ),
            maxLines: 3,
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              if (widget.existing.isNotEmpty)
                TextButton(
                  onPressed: () {
                    Navigator.pop(
                      context,
                      AnnotationToolbarResult(
                        color: _color,
                        delete: true,
                        existingId: _existingId,
                      ),
                    );
                  },
                  child: const Text('삭제'),
                ),
              const Spacer(),
              FilledButton(
                onPressed: () {
                  HapticFeedback.mediumImpact();
                  Navigator.pop(
                    context,
                    AnnotationToolbarResult(
                      color: _color,
                      note: _noteCtrl.text.trim(),
                      existingId: _existingId,
                    ),
                  );
                },
                child: const Text('저장'),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
