/// Dual-wheel header picker (section × position · figure/table × number).
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import '../api/reader_nav_labels.dart';

/// Left wheel: fewer sections — tighter diameter (snappier). Right: smoother spin.
const _leftDiameterRatio = 1.05;
const _rightDiameterRatio = 1.45;
const _itemExtent = 38.0;

/// Section name (left) × sentence index in section (right). Null = cancelled.
Future<int?> showSectionNavPicker({
  required BuildContext context,
  required SectionNavIndex nav,
  required int currentGlobalIndex,
}) async {
  if (nav.isEmpty || nav.sectionCount == 0) return null;
  final initial = nav.selectionForGlobal(currentGlobalIndex);
  final picked = await showModalBottomSheet<(int, int)>(
    context: context,
    showDragHandle: true,
    builder: (ctx) => _DualWheelSheet(
      title: 'Jump to sentence',
      leftCount: nav.sectionCount,
      rightCountForLeft: nav.positionCountForSection,
      leftLabel: nav.sectionLabelAt,
      rightLabel: (left, right) {
        final total = nav.positionCountForSection(left);
        return '${right + 1} / $total';
      },
      initialLeft: initial.$1,
      initialRight: initial.$2,
      leftDiameterRatio: _leftDiameterRatio,
      rightDiameterRatio: _rightDiameterRatio,
    ),
  );
  if (picked == null) return null;
  return nav.globalIndexFor(picked.$1, picked.$2);
}

/// Figure | Table (left) × slot number (right). Null = cancelled.
Future<int?> showFigureNavPicker({
  required BuildContext context,
  required FigureNavIndex nav,
  required int currentCarouselIndex,
}) async {
  if (!nav.hasPicker || nav.kindCount == 0) return null;
  final initial = nav.selectionForCarousel(currentCarouselIndex);
  final picked = await showModalBottomSheet<(int, int)>(
    context: context,
    showDragHandle: true,
    builder: (ctx) => _DualWheelSheet(
      title: 'Jump to figure / table',
      leftCount: nav.kindCount,
      rightCountForLeft: nav.numberCountForKind,
      leftLabel: nav.kindLabelAt,
      rightLabel: (left, right) {
        final total = nav.totalLabelForKind(left);
        final num = nav.numberLabelAt(left, right);
        return '$num / $total';
      },
      initialLeft: initial.$1,
      initialRight: initial.$2,
      leftDiameterRatio: _leftDiameterRatio,
      rightDiameterRatio: _rightDiameterRatio,
    ),
  );
  if (picked == null) return null;
  return nav.carouselIndexFor(picked.$1, picked.$2);
}

class _DualWheelSheet extends StatefulWidget {
  const _DualWheelSheet({
    required this.title,
    required this.leftCount,
    required this.rightCountForLeft,
    required this.leftLabel,
    required this.rightLabel,
    required this.initialLeft,
    required this.initialRight,
    required this.leftDiameterRatio,
    required this.rightDiameterRatio,
  });

  final String title;
  final int Function() leftCount;
  final int Function(int leftIndex) rightCountForLeft;
  final String Function(int leftIndex) leftLabel;
  final String Function(int leftIndex, int rightIndex) rightLabel;
  final int initialLeft;
  final int initialRight;
  final double leftDiameterRatio;
  final double rightDiameterRatio;

  @override
  State<_DualWheelSheet> createState() => _DualWheelSheetState();
}

class _DualWheelSheetState extends State<_DualWheelSheet> {
  late int _left;
  late int _right;
  late FixedExtentScrollController _leftCtrl;
  late FixedExtentScrollController _rightCtrl;

  @override
  void initState() {
    super.initState();
    _left = widget.initialLeft.clamp(0, widget.leftCount() - 1);
    final rightMax = widget.rightCountForLeft(_left);
    _right = widget.initialRight.clamp(0, rightMax > 0 ? rightMax - 1 : 0);
    _leftCtrl = FixedExtentScrollController(initialItem: _left);
    _rightCtrl = FixedExtentScrollController(initialItem: _right);
  }

  @override
  void dispose() {
    _leftCtrl.dispose();
    _rightCtrl.dispose();
    super.dispose();
  }

  void _onLeftChanged(int index) {
    setState(() {
      _left = index;
      final max = widget.rightCountForLeft(_left);
      if (max < 1) {
        _right = 0;
      } else if (_right >= max) {
        _right = max - 1;
      }
      _rightCtrl.dispose();
      _rightCtrl = FixedExtentScrollController(initialItem: _right);
    });
  }

  @override
  Widget build(BuildContext context) {
    final rightCount = widget.rightCountForLeft(_left);
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(8, 0, 8, 8),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              children: [
                TextButton(
                  onPressed: () => Navigator.pop(context),
                  child: const Text('Cancel'),
                ),
                Expanded(
                  child: Text(
                    widget.title,
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.titleSmall,
                  ),
                ),
                TextButton(
                  onPressed: rightCount < 1
                      ? null
                      : () => Navigator.pop(context, (_left, _right)),
                  child: const Text('OK'),
                ),
              ],
            ),
            SizedBox(
              height: 216,
              child: Row(
                children: [
                  Expanded(
                    flex: 3,
                    child: CupertinoPicker(
                      scrollController: _leftCtrl,
                      itemExtent: _itemExtent,
                      diameterRatio: widget.leftDiameterRatio,
                      onSelectedItemChanged: _onLeftChanged,
                      children: List.generate(
                        widget.leftCount(),
                        (i) => Center(
                          child: Text(
                            widget.leftLabel(i),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ),
                    ),
                  ),
                  Expanded(
                    flex: 2,
                    child: CupertinoPicker(
                      scrollController: _rightCtrl,
                      itemExtent: _itemExtent,
                      diameterRatio: widget.rightDiameterRatio,
                      onSelectedItemChanged: (i) => _right = i,
                      children: List.generate(
                        rightCount,
                        (i) => Center(
                          child: Text(widget.rightLabel(_left, i)),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Tappable split header: left title + right counter → opens [onTap].
class ReaderNavHeaderLabel extends StatelessWidget {
  const ReaderNavHeaderLabel({
    super.key,
    required this.left,
    required this.right,
    this.onTap,
    this.enabled = true,
  });

  final String left;
  final String right;
  final VoidCallback? onTap;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    final style = Theme.of(context).textTheme.titleSmall;
    final child = Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Flexible(
          child: Text(
            left,
            style: style,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            textAlign: TextAlign.end,
          ),
        ),
        const SizedBox(width: 10),
        Text(right, style: style),
      ],
    );
    if (!enabled || onTap == null) return child;
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(8),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 6),
          child: child,
        ),
      ),
    );
  }
}
