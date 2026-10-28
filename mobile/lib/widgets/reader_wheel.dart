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
/// drawn there; -1: from above) while the one before slides out the other
/// way. 0 shows it at once — swipes fly sideways on their own and a picker
/// jump is no step. Every slot keeps one shape and the key of its sentence, so
/// a rebuild does not remount a sentence and lose its scroll position.
///
/// design/472 — it ignores "reduce motion": Windows with animation effects off
/// reports it to the browser, and the slide was asked for on such a PC.
/// design/474 — the move starts after the first frame of the new sentence: on
/// the web that frame is slow, and a move started with the build was mostly
/// over before anything was shown.
/// design/475 — the controller keeps its full length: an [AnimationController]
/// runs at 5% of its duration while the platform asks to disable animations,
/// which is the same Windows setting.
class SentenceSlideSwitcher extends StatefulWidget {
  const SentenceSlideSwitcher({super.key, required this.dir, required this.child});

  final int dir;
  final Widget child;

  static const Duration duration = Duration(milliseconds: 280);

  /// How far the sentences travel, in their own heights.
  static const double travel = 0.3;

  @override
  State<SentenceSlideSwitcher> createState() => _SentenceSlideSwitcherState();
}

class _SentenceSlideSwitcherState extends State<SentenceSlideSwitcher>
    with SingleTickerProviderStateMixin {
  late final AnimationController _move = AnimationController(
    vsync: this,
    duration: SentenceSlideSwitcher.duration,
    value: 1,
    animationBehavior: AnimationBehavior.preserve,
  )..addStatusListener((status) {
      if (status == AnimationStatus.completed && _leaving != null && mounted) {
        setState(() => _leaving = null);
      }
    });
  late final Animation<double> _eased =
      CurvedAnimation(parent: _move, curve: Curves.easeOutCubic);
  Widget? _leaving;
  int _dir = 0;
  int _gen = 0;

  @override
  void didUpdateWidget(covariant SentenceSlideSwitcher oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (Widget.canUpdate(oldWidget.child, widget.child)) return;
    _gen++;
    if (widget.dir == 0) {
      _leaving = null;
      _move.value = 1;
      return;
    }
    _leaving = oldWidget.child;
    _dir = widget.dir.sign;
    _move.value = 0;
    final gen = _gen;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && gen == _gen) _move.forward(from: 0);
    });
  }

  @override
  void dispose() {
    _move.dispose();
    super.dispose();
  }

  Widget _slot(Widget child, {required bool leaving}) {
    return KeyedSubtree(
      key: ValueKey<Object?>(child.key),
      child: IgnorePointer(
        ignoring: leaving,
        child: AnimatedBuilder(
          animation: _eased,
          builder: (context, inner) {
            final v = _eased.value;
            final shift = SentenceSlideSwitcher.travel * _dir;
            return FractionalTranslation(
              translation: Offset(0, leaving ? -shift * v : shift * (1 - v)),
              child: Opacity(
                opacity: (leaving ? 1 - v : v).clamp(0.0, 1.0),
                child: inner,
              ),
            );
          },
          child: child,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final leaving = _leaving;
    return ClipRect(
      child: Stack(
        fit: StackFit.passthrough,
        children: [
          if (leaving != null) _slot(leaving, leaving: true),
          _slot(widget.child, leaving: false),
        ],
      ),
    );
  }
}
