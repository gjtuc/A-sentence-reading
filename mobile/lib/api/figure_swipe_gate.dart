/// design/117 — when to allow 1× pan-end figure swipe.
///
/// INVARIANT: multi-touch (pinch) must never change figure index, even if
/// scale returns to 1× while fingers are still down.
library;

/// Returns true only for a **single-pointer** pan that ended at ~1× scale.
///
/// [maxPointerCount] is the peak pointer count observed during the gesture
/// (from [ScaleStartDetails]/[ScaleUpdateDetails].pointerCount).
bool allowFigureSwipeAfterPan({
  required int maxPointerCount,
  required double scale,
  double zoomEps = 1.02,
}) {
  // WHY: two-finger pinch-out to 1× still has residual translation; must not
  // look like a one-finger swipe (design/117).
  if (maxPointerCount >= 2) return false;
  // EDGE: still zoomed — pan moves the figure, never advances index.
  if (scale > zoomEps) return false;
  // EDGE: bogus / missing pointer samples — fail closed (no accidental advance).
  if (maxPointerCount < 1) return false;
  return true;
}
