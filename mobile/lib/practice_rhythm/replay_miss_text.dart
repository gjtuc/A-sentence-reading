/// Replay blink for content words the take did not cover.
library;

import 'package:flutter/material.dart';

import '../practice_skill/skill_score.dart';
import 'rhythm_theme.dart';

const Color kReplayMiss = Color(0xFFFF4D4D);

class ReplayMissText extends StatefulWidget {
  const ReplayMissText({
    super.key,
    required this.text,
    required this.misses,
    required this.blink,
    required this.style,
  });

  final String text;
  final List<MissedWordSpan> misses;
  final bool blink;
  final TextStyle style;

  @override
  State<ReplayMissText> createState() => _ReplayMissTextState();
}

class _ReplayMissTextState extends State<ReplayMissText>
    with SingleTickerProviderStateMixin {
  late final AnimationController _blink;

  @override
  void initState() {
    super.initState();
    _blink = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 520),
    );
    if (widget.blink && widget.misses.isNotEmpty) {
      _blink.repeat(reverse: true);
    }
  }

  @override
  void didUpdateWidget(ReplayMissText oldWidget) {
    super.didUpdateWidget(oldWidget);
    final on = widget.blink && widget.misses.isNotEmpty;
    if (on && !_blink.isAnimating) {
      _blink.repeat(reverse: true);
    } else if (!on && _blink.isAnimating) {
      _blink.stop();
      _blink.value = 0;
    }
  }

  @override
  void dispose() {
    _blink.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.blink || widget.misses.isEmpty) {
      return Text(
        widget.text,
        textAlign: TextAlign.center,
        style: widget.style,
      );
    }
    return AnimatedBuilder(
      animation: _blink,
      builder: (context, _) {
        final color = Color.lerp(kRhythmText, kReplayMiss, _blink.value)!;
        return Text.rich(
          TextSpan(children: _spans(color)),
          textAlign: TextAlign.center,
          style: widget.style,
        );
      },
    );
  }

  List<InlineSpan> _spans(Color missColor) {
    final out = <InlineSpan>[];
    var cursor = 0;
    for (final span in widget.misses) {
      if (span.start < cursor || span.end > widget.text.length) continue;
      if (span.start > cursor) {
        out.add(TextSpan(text: widget.text.substring(cursor, span.start)));
      }
      out.add(
        TextSpan(
          text: widget.text.substring(span.start, span.end),
          style: widget.style.copyWith(color: missColor),
        ),
      );
      cursor = span.end;
    }
    if (cursor < widget.text.length) {
      out.add(TextSpan(text: widget.text.substring(cursor)));
    }
    return out;
  }
}
