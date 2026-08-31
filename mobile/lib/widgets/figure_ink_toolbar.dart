import 'package:flutter/material.dart';

import '../api/figure_ink_models.dart';

/// Slides open below the figure header when ink mode is on.
class FigureInkToolbar extends StatelessWidget {
  const FigureInkToolbar({
    super.key,
    required this.expanded,
    required this.tool,
    required this.colorHex,
    required this.onToolChanged,
    required this.onColorChanged,
  });

  final bool expanded;
  final FigureInkTool tool;
  final String colorHex;
  final ValueChanged<FigureInkTool> onToolChanged;
  final ValueChanged<String> onColorChanged;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return AnimatedSize(
      duration: const Duration(milliseconds: 200),
      curve: Curves.easeInOut,
      alignment: Alignment.topCenter,
      child: expanded
          ? Padding(
              padding: const EdgeInsets.fromLTRB(8, 0, 8, 6),
              child: Material(
                elevation: 0,
                color: scheme.surfaceContainerHighest.withValues(alpha: 0.92),
                borderRadius: BorderRadius.circular(10),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
                  child: Row(
                    children: [
                      _ToolChip(
                        tooltip: '펜',
                        icon: Icons.edit_outlined,
                        selected: tool == FigureInkTool.pen,
                        onTap: () => onToolChanged(FigureInkTool.pen),
                      ),
                      const SizedBox(width: 4),
                      Expanded(
                        child: SingleChildScrollView(
                          scrollDirection: Axis.horizontal,
                          child: Row(
                            children: [
                              for (final hex in figureInkPalette)
                                Padding(
                                  padding: const EdgeInsets.only(right: 8),
                                  child: _ColorDot(
                                    hex: hex,
                                    selected: colorHex.toUpperCase() ==
                                        hex.toUpperCase(),
                                    onTap: () => onColorChanged(hex),
                                  ),
                                ),
                            ],
                          ),
                        ),
                      ),
                      _ToolChip(
                        tooltip: '지우개',
                        icon: Icons.auto_fix_off_outlined,
                        selected: tool == FigureInkTool.eraser,
                        onTap: () => onToolChanged(FigureInkTool.eraser),
                      ),
                    ],
                  ),
                ),
              ),
            )
          : const SizedBox(width: double.infinity),
    );
  }
}

class _ToolChip extends StatelessWidget {
  const _ToolChip({
    required this.tooltip,
    required this.icon,
    required this.selected,
    required this.onTap,
  });

  final String tooltip;
  final IconData icon;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Tooltip(
      message: tooltip,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(8),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            color: selected
                ? scheme.primary.withValues(alpha: 0.18)
                : Colors.transparent,
            borderRadius: BorderRadius.circular(8),
          ),
          child: Icon(
            icon,
            size: 22,
            color: selected ? scheme.primary : scheme.onSurfaceVariant,
          ),
        ),
      ),
    );
  }
}

class _ColorDot extends StatelessWidget {
  const _ColorDot({
    required this.hex,
    required this.selected,
    required this.onTap,
  });

  final String hex;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final fill = figureInkColorValue(hex);
    final needsBorder = hex.toUpperCase() == '#FFFFFF' ||
        hex.toUpperCase() == '#FDD835';
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        width: 28,
        height: 28,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: fill,
          border: Border.all(
            color: selected
                ? Theme.of(context).colorScheme.primary
                : (needsBorder
                    ? Theme.of(context).colorScheme.outline
                    : Colors.transparent),
            width: selected ? 2.5 : 1,
          ),
        ),
      ),
    );
  }
}
