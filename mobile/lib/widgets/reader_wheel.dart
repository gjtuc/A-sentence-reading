/// design/471 — the mouse wheel turns sentences and figures like ←/→, and a
/// one-step move slides the sentence in from where it was drawn.
library;

import 'package:flutter/gestures.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

/// Wheel events → at most one step per turn.
///
/// A wheel notch arrives as one event, a touchpad swipe as dozens of small ones
/// with inertia. Events closer than [gestureGap] are one turn: it steps once,
/// then again only every [repeat] while it lasts. A turn that an inner scroller
/// used (a long sentence scrolling to its end) does not step; the next turn does.
class WheelStepper {
  WheelStepper({
    this.threshold = 30,
    this.gestureGap = const Duration(milliseconds: 160),
    this.repeat = const Duration(milliseconds: 420),
    this.minGap = const Duration(milliseconds: 120),
  });

  final double threshold;
  final Duration gestureGap;
  final Duration repeat;
  final Duration minGap;

  Duration? _lastSeen;
  Duration? _lastMove;
  double _acc = 0;
  bool _pendingWin = false;
  bool _innerThisTurn = false;
  bool _newTurn = true;

  /// Every wheel event over the pane, before anyone claims it.
  void seen(Duration t) {
    final last = _lastSeen;
    _newTurn = last == null || t - last > gestureGap;
    if (_newTurn) {
      _innerThisTurn = false;
      _acc = 0;
    } else if (_pendingWin) {
      _innerThisTurn = true;
    }
    _pendingWin = true;
    _lastSeen = t;
  }

  /// The pane got the event: -1, 0 or 1.
  int won(Duration t, double dy) {
    _pendingWin = false;
    if (_innerThisTurn) return 0;
    final last = _lastMove;
    if (last != null && t - last < (_newTurn ? minGap : repeat)) return 0;
    _acc += dy;
    if (_acc.abs() < threshold) return 0;
    final step = _acc > 0 ? 1 : -1;
    _acc = 0;
    _lastMove = t;
    return step;
  }
}

/// Wheel down → [onStep] (1), up → (-1). A scroller inside that can still move
/// gets the wheel first (it claims the event before this does). Ctrl+wheel is
/// left alone: it zooms a figure.
class WheelPager extends StatefulWidget {
  const WheelPager({super.key, required this.child, this.onStep});

  final Widget child;
  final ValueChanged<int>? onStep;

  @override
  State<WheelPager> createState() => _WheelPagerState();
}

class _WheelPagerState extends State<WheelPager> {
  final WheelStepper _stepper = WheelStepper();

  void _onSignal(PointerSignalEvent event) {
    if (event is! PointerScrollEvent || widget.onStep == null) return;
    final d = event.scrollDelta;
    if (d.dy == 0 || d.dx.abs() > d.dy.abs()) return;
    if (HardwareKeyboard.instance.isControlPressed) return;
    _stepper.seen(event.timeStamp);
    GestureBinding.instance.pointerSignalResolver.register(event, (e) {
      final step = _stepper.won(e.timeStamp, (e as PointerScrollEvent).scrollDelta.dy);
      if (step != 0) widget.onStep?.call(step);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Listener(onPointerSignal: _onSignal, child: widget.child);
  }
}

/// The sentence slides in by [dir] (1: from below, as the next sentence was
/// drawn there; -1: from above). 0 shows it at once — swipes fly sideways on
/// their own and a picker jump is no step. The transition keeps one shape for
/// every [dir], so a later rebuild does not remount the sentence and lose its
/// scroll position.
class SentenceSlideSwitcher extends StatelessWidget {
  const SentenceSlideSwitcher({super.key, required this.dir, required this.child});

  final int dir;
  final Widget child;

  static const Duration duration = Duration(milliseconds: 200);

  @override
  Widget build(BuildContext context) {
    final still = dir == 0 || (MediaQuery.maybeDisableAnimationsOf(context) ?? false);
    return AnimatedSwitcher(
      duration: still ? Duration.zero : duration,
      switchInCurve: Curves.easeOutCubic,
      layoutBuilder: (current, previous) => current ?? const SizedBox.shrink(),
      transitionBuilder: (child, animation) => FadeTransition(
        opacity: Tween<double>(begin: still ? 1 : 0.35, end: 1).animate(animation),
        child: SlideTransition(
          position: Tween<Offset>(
            begin: Offset(0, still ? 0 : 0.12 * dir.sign),
            end: Offset.zero,
          ).animate(animation),
          child: child,
        ),
      ),
      child: child,
    );
  }
}
