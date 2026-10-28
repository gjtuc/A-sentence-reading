/// design/471 — the mouse wheel turns sentences and figures like ←/→, and a
/// one-step move changes the sentence in place (design/480).
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

/// The sentence after a step of [dir] (1 or -1) takes the old one's place
/// without moving: the old one dims to [floor], the new one replaces it there
/// and brightens. 0 shows it at once — swipes fly sideways on their own and a
/// picker jump is no step. Every slot keeps one shape and the key of its
/// sentence, so a rebuild does not remount a sentence and lose its scroll
/// position.
///
/// design/472 — it ignores "reduce motion": Windows with animation effects off
/// reports it to the browser, and the step was asked for on such a PC.
/// design/474 — the change starts after the first frame of the new sentence: on
/// the web that frame is slow, and a change started with the build was mostly
/// over before anything was shown.
/// design/475 — the controller keeps its full length: an [AnimationController]
/// runs at 5% of its duration while the platform asks to disable animations,
/// which is the same Windows setting.
/// design/480 — no slide at all: moving text pulls the eyes along with it
/// whether the reader wants it or not, and that tired them. The two sentences
/// never show together (they start at one place and would pile up), and the
/// pane never drops below [floor] of one sentence, which read as a blink.
class SentenceFadeSwitcher extends StatefulWidget {
  const SentenceFadeSwitcher({super.key, required this.dir, required this.child});

  final int dir;
  final Widget child;

  static const Duration duration = Duration(milliseconds: 260);

  /// The least opacity on screen: the old sentence's at the swap, the new
  /// one's right after it.
  static const double floor = 0.4;

  /// The share of [duration] the old sentence dims for.
  static const double swapAt = 0.4;

  /// Opacities of the old and the new sentence [t] of the way through.
  static ({double old, double fresh}) inkAt(double t) {
    if (t >= 1) return (old: 0, fresh: 1);
    if (t < swapAt) {
      return (old: 1 - (1 - floor) * Curves.easeOut.transform(t / swapAt), fresh: 0);
    }
    return (old: 0, fresh: floor + (1 - floor) * Curves.easeOut.transform((t - swapAt) / (1 - swapAt)));
  }

  @override
  State<SentenceFadeSwitcher> createState() => _SentenceFadeSwitcherState();
}

class _SentenceFadeSwitcherState extends State<SentenceFadeSwitcher>
    with SingleTickerProviderStateMixin {
  late final AnimationController _fade = AnimationController(
    vsync: this,
    duration: SentenceFadeSwitcher.duration,
    value: 1,
    animationBehavior: AnimationBehavior.preserve,
  )..addStatusListener((status) {
      if (status == AnimationStatus.completed && _leaving != null && mounted) {
        setState(() => _leaving = null);
      }
    });
  Widget? _leaving;
  int _gen = 0;

  @override
  void didUpdateWidget(covariant SentenceFadeSwitcher oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (Widget.canUpdate(oldWidget.child, widget.child)) return;
    _gen++;
    if (widget.dir == 0) {
      _leaving = null;
      _fade.value = 1;
      return;
    }
    _leaving = oldWidget.child;
    _fade.value = 0;
    final gen = _gen;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && gen == _gen) _fade.forward(from: 0);
    });
  }

  @override
  void dispose() {
    _fade.dispose();
    super.dispose();
  }

  Widget _slot(Widget child, {required bool leaving}) {
    return KeyedSubtree(
      key: ValueKey<Object?>(child.key),
      child: IgnorePointer(
        ignoring: leaving,
        child: AnimatedBuilder(
          animation: _fade,
          builder: (context, inner) {
            final ink = _leaving == null
                ? (old: 0.0, fresh: 1.0)
                : SentenceFadeSwitcher.inkAt(_fade.value);
            return Opacity(
              opacity: (leaving ? ink.old : ink.fresh).clamp(0.0, 1.0),
              child: inner,
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
