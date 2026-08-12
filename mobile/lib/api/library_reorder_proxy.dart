/// design/122 — drag proxy for library reorder (no white Material flash).
library;

import 'dart:ui' show lerpDouble;

import 'package:flutter/material.dart';

/// Builds the floating row while reordering.
///
/// WHY: Flutter's default [SliverReorderableList] proxy uses Material 3
/// elevation + surface tint, which flashes opaque white on many themes.
/// We keep a lifted row (elevation) but pin surface to the theme and
/// disable surface tint so the drag preview matches the list.
Widget libraryReorderProxyDecorator(
  Widget child,
  int index,
  Animation<double> animation, {
  required ColorScheme colorScheme,
  Color? shadowColor,
}) {
  // EDGE: index unused — signature matches proxyDecorator callback.
  assert(index >= 0);
  return AnimatedBuilder(
    animation: animation,
    builder: (context, child) {
      final t = Curves.easeInOut.transform(animation.value);
      final elevation = lerpDouble(0, 6, t) ?? 0;
      return Material(
        elevation: elevation,
        // Fail-closed against white flash: never rely on default tinted surface.
        color: colorScheme.surface,
        surfaceTintColor: Colors.transparent,
        shadowColor: shadowColor ?? colorScheme.shadow,
        child: child,
      );
    },
    child: child,
  );
}
