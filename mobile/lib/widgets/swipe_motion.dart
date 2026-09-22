/// Horizontal page swipe: follow the finger, then spring back or fly off.
library;

/// Finger travel with tightening resistance. No rotation.
double rubberBandOffset(double dx, double width) {
  if (!dx.isFinite || dx == 0) return 0;
  final span = width.isFinite && width > 0 ? width : dx.abs();
  final sign = dx.sign;
  final x = dx.abs();
  final t = x / span;
  return sign * (x / (1 + t * 0.65));
}

/// Off-screen x for a committed swipe. Negative flies left (next).
double flingTarget(double dx, double width) {
  if (dx == 0 || !dx.isFinite) return 0;
  final span = width.isFinite && width > 0 ? width : 800.0;
  return dx.sign * span * 1.15;
}
