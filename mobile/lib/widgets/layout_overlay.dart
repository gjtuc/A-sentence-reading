/// design/151 — normalized layout bbox overlay on PDF page preview.
library;

import 'package:flutter/material.dart';

/// One layout box from layout_map.json (rect in page-normalized 0–1 coords).
class LayoutBoxView {
  LayoutBoxView({
    required this.id,
    required this.pageIndex,
    required this.kind,
    required this.left,
    required this.top,
    required this.right,
    required this.bottom,
    this.text = '',
  });

  factory LayoutBoxView.fromJson(
    Map<String, dynamic> json, {
    required int pageW,
    required int pageH,
  }) {
    final rect = json['rect'];
    final map = rect is Map ? rect : const {};
    final x0 = (map['x0'] as num?)?.toDouble() ?? 0;
    final y0 = (map['y0'] as num?)?.toDouble() ?? 0;
    final x1 = (map['x1'] as num?)?.toDouble() ?? 0;
    final y1 = (map['y1'] as num?)?.toDouble() ?? 0;
    final pw = pageW > 0 ? pageW.toDouble() : 1.0;
    final ph = pageH > 0 ? pageH.toDouble() : 1.0;
    return LayoutBoxView(
      id: '${json['id'] ?? ''}',
      pageIndex: (json['page_index'] as num?)?.toInt() ?? 0,
      kind: '${json['kind'] ?? 'paragraph'}',
      left: x0 / pw,
      top: y0 / ph,
      right: x1 / pw,
      bottom: y1 / ph,
      text: '${json['text'] ?? ''}',
    );
  }

  final String id;
  final int pageIndex;
  final String kind;
  final double left;
  final double top;
  final double right;
  final double bottom;
  final String text;

  Color get color {
    switch (kind) {
      case 'figure_body':
        return Colors.blue.withValues(alpha: 0.35);
      case 'table_body':
        return Colors.green.withValues(alpha: 0.35);
      case 'figure_caption':
        return Colors.orange.withValues(alpha: 0.45);
      case 'table_caption':
        return Colors.teal.withValues(alpha: 0.45);
      default:
        return Colors.grey.withValues(alpha: 0.25);
    }
  }
}

/// Stack colored hit boxes over a child (typically page image placeholder).
class LayoutOverlay extends StatelessWidget {
  const LayoutOverlay({
    super.key,
    required this.boxes,
    required this.pageIndex,
    this.onBoxTap,
    this.selectedIds = const {},
    this.child,
  });

  final List<LayoutBoxView> boxes;
  final int pageIndex;
  final void Function(LayoutBoxView box)? onBoxTap;
  final Set<String> selectedIds;
  final Widget? child;

  @override
  Widget build(BuildContext context) {
    final visible = boxes.where((b) => b.pageIndex == pageIndex).toList();
    return LayoutBuilder(
      builder: (context, constraints) {
        final w = constraints.maxWidth;
        final h = constraints.maxHeight;
        return Stack(
          fit: StackFit.expand,
          children: [
            if (child != null) child!,
            for (final box in visible)
              Positioned(
                left: box.left * w,
                top: box.top * h,
                width: (box.right - box.left).clamp(0.02, 1.0) * w,
                height: (box.bottom - box.top).clamp(0.02, 1.0) * h,
                child: GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: onBoxTap == null ? null : () => onBoxTap!(box),
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      border: Border.all(
                        color: selectedIds.contains(box.id)
                            ? Colors.amber.shade700
                            : box.color.withValues(alpha: 0.9),
                        width: selectedIds.contains(box.id) ? 3 : 2,
                      ),
                      color: box.color,
                    ),
                  ),
                ),
              ),
          ],
        );
      },
    );
  }
}
