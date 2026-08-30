/// design/118 — map raw pinch scale to a stronger, still-stable factor.
///
/// [ScaleUpdateDetails.scale] is 1.0 at gesture start; values &gt;1 zoom in.
library;

import 'dart:math' as math;

/// Product lock: **확실히 체감** (not a subtle nudge).
///
/// Applied as `pow(rawScale, k)` so 1.0 stays fixed and both zoom-in and
/// zoom-out accelerate symmetrically on a log scale.
const double kFigurePinchSensitivity = 1.85;

/// Same product lock as pinch — zoomed pan should feel equally responsive.
const double kFigurePanSensitivity = kFigurePinchSensitivity;

/// Returns the relative scale to apply on top of the scale at gesture start.
///
/// [rawScale] comes from [ScaleUpdateDetails.scale] (1.0 at start).
double amplifyFigurePinchScale({
  required double rawScale,
  double sensitivity = kFigurePinchSensitivity,
}) {
  // EDGE: NaN / non-finite / non-positive — fail closed to identity (no jump).
  if (!rawScale.isFinite || rawScale <= 0) return 1.0;
  // EDGE: bogus sensitivity — treat as 1:1 (safer than exploding zoom).
  if (!sensitivity.isFinite || sensitivity <= 0) return rawScale;
  // WHY: keep the gesture origin fixed so tiny tracker noise does not drift.
  if ((rawScale - 1.0).abs() < 1e-6) return 1.0;
  // WHY: exponent > 1 → same finger travel feels stronger (design/118).
  return math.pow(rawScale, sensitivity).toDouble();
}

/// Extra pan multiplier on top of [InteractiveViewer]'s 1:1 drag when zoomed.
///
/// [delta] is logical px moved this frame; returns the **additional** px to apply
/// so total travel ≈ `delta * sensitivity`.
double amplifyFigurePanExtraDelta({
  required double delta,
  double sensitivity = kFigurePanSensitivity,
}) {
  if (!delta.isFinite) return 0.0;
  if (!sensitivity.isFinite || sensitivity <= 1.0) return 0.0;
  return delta * (sensitivity - 1.0);
}
