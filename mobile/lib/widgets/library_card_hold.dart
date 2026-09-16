import 'package:flutter/gestures.dart';
import 'package:flutter/widgets.dart';

/// design/308 — 500ms hold shows a menu; move without lifting starts a drag.
///
/// Scroll still wins if the finger moves past the touch slop before the hold.
class LibraryCardHold extends StatefulWidget {
  const LibraryCardHold({
    super.key,
    required this.enabled,
    required this.onHold,
    required this.onDragStart,
    required this.onDragUpdate,
    required this.onDragEnd,
    required this.onCancel,
    required this.child,
  });

  final bool enabled;
  final ValueSetter<Offset> onHold;
  final ValueSetter<Offset> onDragStart;
  final ValueSetter<Offset> onDragUpdate;
  final ValueSetter<Offset> onDragEnd;
  final VoidCallback onCancel;
  final Widget child;

  @override
  State<LibraryCardHold> createState() => _LibraryCardHoldState();
}

class _LibraryCardHoldState extends State<LibraryCardHold> {
  Offset? _origin;
  bool _dragging = false;

  void _hold(Offset pos) {
    _origin = pos;
    _dragging = false;
    if (!widget.enabled) return;
    widget.onHold(pos);
  }

  void _move(Offset pos) {
    if (!widget.enabled) return;
    final origin = _origin ?? pos;
    if (!_dragging && (pos - origin).distance < 12) return;
    if (!_dragging) {
      _dragging = true;
      widget.onDragStart(pos);
      return;
    }
    widget.onDragUpdate(pos);
  }

  void _end(Offset pos) {
    if (_dragging && widget.enabled) widget.onDragEnd(pos);
    _dragging = false;
    _origin = null;
  }

  void _cancel() {
    final was = _dragging;
    _dragging = false;
    _origin = null;
    if (was) widget.onCancel();
  }

  @override
  Widget build(BuildContext context) {
    return RawGestureDetector(
      behavior: HitTestBehavior.translucent,
      gestures: <Type, GestureRecognizerFactory>{
        LongPressGestureRecognizer:
            GestureRecognizerFactoryWithHandlers<LongPressGestureRecognizer>(
          () => LongPressGestureRecognizer(
            duration: const Duration(milliseconds: 500),
          ),
          (instance) {
            instance.onLongPressStart = widget.enabled ? (d) => _hold(d.globalPosition) : null;
            instance.onLongPressMoveUpdate =
                widget.enabled ? (d) => _move(d.globalPosition) : null;
            instance.onLongPressEnd = widget.enabled ? (d) => _end(d.globalPosition) : null;
            instance.onLongPressCancel = _cancel;
          },
        ),
      },
      child: widget.child,
    );
  }
}
