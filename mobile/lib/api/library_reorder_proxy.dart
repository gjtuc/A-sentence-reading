/// design/122 — drag proxy for library reorder (no white Material flash).
library;

import 'dart:ui' show lerpDouble;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Builds the floating lifted row while reordering with lift scale, border highlight & shadow.
///
/// WHY: Flutter's default [SliverReorderableList] proxy uses Material 3
/// elevation + surface tint, which flashes opaque white on many themes.
/// We keep a lifted row (elevation + scale) but pin surface to the theme,
/// add a subtle primary border highlight, and disable surface tint.
Widget libraryReorderProxyDecorator(
  Widget child,
  int index,
  Animation<double> animation, {
  required ColorScheme colorScheme,
  Color? shadowColor,
  ValueListenable<bool>? isLifted,
}) {
  // EDGE: index unused — signature matches proxyDecorator callback.
  assert(index >= 0);
  return _LibraryReorderProxyWidget(
    animation: animation,
    colorScheme: colorScheme,
    shadowColor: shadowColor,
    isLifted: isLifted,
    child: child,
  );
}

class _LibraryReorderProxyWidget extends StatefulWidget {
  const _LibraryReorderProxyWidget({
    required this.child,
    required this.animation,
    required this.colorScheme,
    this.shadowColor,
    this.isLifted,
  });

  final Widget child;
  final Animation<double> animation;
  final ColorScheme colorScheme;
  final Color? shadowColor;
  final ValueListenable<bool>? isLifted;

  @override
  State<_LibraryReorderProxyWidget> createState() =>
      _LibraryReorderProxyWidgetState();
}

class _LibraryReorderProxyWidgetState
    extends State<_LibraryReorderProxyWidget> {
  @override
  void initState() {
    super.initState();
    if (widget.isLifted == null) {
      // Physical "pick up & lift" haptic feedback on drag pickup if not decoupled.
      HapticFeedback.mediumImpact();
    }
  }

  @override
  Widget build(BuildContext context) {
    final liftedListenable = widget.isLifted ?? ValueNotifier<bool>(true);

    return ValueListenableBuilder<bool>(
      valueListenable: liftedListenable,
      builder: (context, lifted, _) {
        return AnimatedBuilder(
          animation: widget.animation,
          builder: (context, _) {
            // When not yet lifted (static finger holding before drag motion),
            // show zero elevation, 1.0 scale and no border (stealth mode for 2s hold).
            final t = lifted
                ? Curves.easeOutCubic.transform(widget.animation.value)
                : 0.0;
            final elevation = lerpDouble(0, 10, t) ?? 0;
            final scale = lerpDouble(1.0, 1.04, t) ?? 1.0;
            return Transform.scale(
              key: const Key('reorder_proxy_transform'),
              scale: scale,
              child: Material(
                elevation: elevation,
                // Fail-closed against white flash: never rely on default tinted surface.
                color: widget.colorScheme.surface,
                surfaceTintColor: Colors.transparent,
                shadowColor: widget.shadowColor ?? widget.colorScheme.shadow,
                borderRadius: BorderRadius.circular(12),
                clipBehavior: Clip.antiAlias,
                child: Container(
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: lifted
                          ? widget.colorScheme.primary
                              .withValues(alpha: t * 0.9)
                          : Colors.transparent,
                      width: 2,
                    ),
                  ),
                  child: widget.child,
                ),
              ),
            );
          },
        );
      },
    );
  }
}
