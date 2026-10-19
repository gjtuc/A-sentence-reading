import 'package:flutter/widgets.dart';

/// design/418 — when the practice clock stops for the app leaving the screen.
///
/// A phone goes inactive when another app or the shade covers it. A browser
/// window goes inactive whenever another window takes focus, such as the figure
/// window on the second monitor, so on the web only a hidden tab stops.
bool practicePausesOn(AppLifecycleState state, {required bool web}) {
  if (state == AppLifecycleState.paused) return true;
  return web
      ? state == AppLifecycleState.hidden
      : state == AppLifecycleState.inactive;
}
