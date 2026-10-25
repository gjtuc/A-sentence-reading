import 'package:flutter/material.dart';

/// design/452 — one colour for 다 읽음, apart from the green of 이미 보관.
final Color kReadDoneColor = Colors.blue.shade600;

/// design/442 — "다 읽음" next to a paper the reader finished.
class ReadDoneBadge extends StatelessWidget {
  const ReadDoneBadge({super.key});

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: '다 읽음',
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
        decoration: BoxDecoration(
          color: kReadDoneColor.withValues(alpha: 0.16),
          border: Border.all(color: kReadDoneColor),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.check_circle, size: 15, color: kReadDoneColor),
            const SizedBox(width: 3),
            Text(
              '다 읽음',
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w700,
                color: kReadDoneColor,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// design/452 — a finished paper's row gets a blue bar down its left edge, so it
/// shows from across the list next to the green border of 이미 보관.
class ReadDoneStripe extends StatelessWidget {
  const ReadDoneStripe({super.key, required this.on, required this.child});

  final bool on;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    if (!on) return child;
    return Stack(
      children: [
        child,
        Positioned(
          key: const ValueKey('read_done_stripe'),
          left: 0,
          top: 0,
          bottom: 0,
          child: Container(
            width: 6,
            decoration: BoxDecoration(
              color: kReadDoneColor,
              borderRadius: const BorderRadius.horizontal(left: Radius.circular(8)),
            ),
          ),
        ),
      ],
    );
  }
}
