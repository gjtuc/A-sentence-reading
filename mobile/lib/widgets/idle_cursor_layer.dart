import 'package:flutter/material.dart';

/// design/423 - hides the mouse cursor over [child] while [hidden]. The cursor
/// sits on a see-through layer above [child], so a button or sentence under a
/// resting pointer cannot keep its own cursor. Clicks still reach [child].
class IdleCursorLayer extends StatelessWidget {
  const IdleCursorLayer({super.key, required this.hidden, required this.child});

  final bool hidden;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.passthrough,
      children: [
        child,
        Positioned.fill(
          child: MouseRegion(
            opaque: false,
            cursor: hidden ? SystemMouseCursors.none : MouseCursor.defer,
          ),
        ),
      ],
    );
  }
}
