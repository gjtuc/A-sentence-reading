/// Replay blink for content words the take did not cover.
library;

import 'package:flutter/material.dart';

import '../practice_skill/skill_score.dart';
import 'rhythm_theme.dart';

const Color kPracticeMark = Color(0x66F5C16C);

class ReplayMissText extends StatefulWidget {
  const ReplayMissText({
    super.key,
    required this.text,
    required this.misses,
    required this.blink,
    required this.style,
    this.follow,
  });

  final String text;
  final List<MissedWordSpan> misses;
  final bool blink;
  final TextStyle style;
  /// Printed range to light during listen/speak. Null during replay.
  final ({int start, int end})? follow;

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
    final follow = widget.follow;
    if (!widget.blink || widget.misses.isEmpty) {
      if (follow == null) {
        return Text(
          widget.text,
          textAlign: TextAlign.center,
          style: widget.style,
        );
      }
      return Text.rich(
        TextSpan(children: _followSpans(follow)),
        textAlign: TextAlign.center,
        style: widget.style,
      );
    }
    return AnimatedBuilder(
      animation: _blink,
      builder: (context, _) {
        final wash = Color.lerp(
          const Color(0x33F5C16C),
          kPracticeMark,
          _blink.value,
        )!;
        return Text.rich(
          TextSpan(children: _spans(wash)),
          textAlign: TextAlign.center,
          style: widget.style,
        );
      },
    );
  }

  List<InlineSpan> _followSpans(({int start, int end}) follow) {
    final text = widget.text;
    final start = follow.start.clamp(0, text.length);
    final end = follow.end.clamp(start, text.length);
    if (end <= start) {
      return [TextSpan(text: text)];
    }
    return [
      if (start > 0) TextSpan(text: text.substring(0, start)),
      TextSpan(
        text: text.substring(start, end),
        style: widget.style.copyWith(color: kRhythmSpeak),
      ),
      if (end < text.length) TextSpan(text: text.substring(end)),
    ];
  }

  List<InlineSpan> _spans(Color wash) {
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
          style: widget.style.copyWith(backgroundColor: wash),
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
