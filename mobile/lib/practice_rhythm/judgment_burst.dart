/// design/214 — center judgment burst (pop + fade).
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'judgment_tier.dart';
import 'rhythm_theme.dart';

class JudgmentBurstData {
  const JudgmentBurstData({
    required this.id,
    required this.tier,
    required this.copy,
    required this.accuracyPct,
  });

  final int id;
  final JudgmentTier tier;
  final String copy;
  final int accuracyPct;
}

Color judgmentColor(JudgmentTier tier) {
  switch (tier) {
    case JudgmentTier.good:
      return kRhythmGood;
    case JudgmentTier.great:
      return kRhythmGreat;
    case JudgmentTier.perfect:
      return kRhythmPerfect;
  }
}

Duration judgmentHold(JudgmentTier tier) {
  switch (tier) {
    case JudgmentTier.good:
      return kJudgmentHoldGood;
    case JudgmentTier.great:
      return kJudgmentHoldGreat;
    case JudgmentTier.perfect:
      return kJudgmentHoldPerfect;
  }
}

void judgmentHaptic(JudgmentTier tier) {
  switch (tier) {
    case JudgmentTier.good:
      HapticFeedback.lightImpact();
      break;
    case JudgmentTier.great:
      HapticFeedback.mediumImpact();
      break;
    case JudgmentTier.perfect:
      HapticFeedback.heavyImpact();
      break;
  }
}

/// Overlay text; parent should wrap with [IgnorePointer].
class JudgmentBurst extends StatefulWidget {
  const JudgmentBurst({
    super.key,
    required this.data,
    this.onFinished,
  });

  final JudgmentBurstData data;
  final VoidCallback? onFinished;

  @override
  State<JudgmentBurst> createState() => _JudgmentBurstState();
}

class _JudgmentBurstState extends State<JudgmentBurst>
    with SingleTickerProviderStateMixin {
  late final AnimationController _c;
  late final Animation<double> _scale;
  late final Animation<double> _opacity;

  @override
  void initState() {
    super.initState();
    final holdMs = judgmentHold(widget.data.tier).inMilliseconds;
    final popMs = kJudgmentPop.inMilliseconds;
    final fadeMs = kJudgmentFade.inMilliseconds;
    final total = Duration(milliseconds: popMs + holdMs + fadeMs);
    _c = AnimationController(vsync: this, duration: total);
    _scale = TweenSequence<double>([
      TweenSequenceItem(
        tween: Tween(begin: 0.75, end: 1.08)
            .chain(CurveTween(curve: Curves.easeOutBack)),
        weight: popMs.toDouble(),
      ),
      TweenSequenceItem(
        tween: Tween(begin: 1.08, end: 1.0),
        weight: 40,
      ),
      TweenSequenceItem(
        tween: ConstantTween(1.0),
        weight: (holdMs - 40).clamp(1, 100000).toDouble(),
      ),
      TweenSequenceItem(
        tween: Tween(begin: 1.0, end: 0.96),
        weight: fadeMs.toDouble(),
      ),
    ]).animate(_c);
    _opacity = TweenSequence<double>([
      TweenSequenceItem(
        tween: Tween(begin: 0.0, end: 1.0),
        weight: popMs.toDouble(),
      ),
      TweenSequenceItem(
        tween: ConstantTween(1.0),
        weight: holdMs.toDouble(),
      ),
      TweenSequenceItem(
        tween: Tween(begin: 1.0, end: 0.0)
            .chain(CurveTween(curve: Curves.easeOut)),
        weight: fadeMs.toDouble(),
      ),
    ]).animate(_c);
    judgmentHaptic(widget.data.tier);
    _c.forward().whenComplete(() {
      if (mounted) widget.onFinished?.call();
    });
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final color = judgmentColor(widget.data.tier);
    return AnimatedBuilder(
      animation: _c,
      builder: (context, child) {
        return Opacity(
          opacity: _opacity.value.clamp(0.0, 1.0),
          child: Transform.translate(
            offset: Offset(0, -8 * (1 - _opacity.value.clamp(0.0, 1.0))),
            child: Transform.scale(
              scale: _scale.value,
              child: child,
            ),
          ),
        );
      },
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            widget.data.copy,
            textAlign: TextAlign.center,
            style: TextStyle(
              color: color,
              fontSize: 34,
              fontWeight: FontWeight.w700,
              letterSpacing: 0.6,
              height: 1.1,
              shadows: [
                Shadow(
                  color: Colors.black.withValues(alpha: 0.55),
                  blurRadius: 8,
                ),
              ],
            ),
          ),
          const SizedBox(height: 4),
          Text(
            '${widget.data.accuracyPct}%',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: color.withValues(alpha: 0.75),
              fontSize: 12,
              fontWeight: FontWeight.w500,
              letterSpacing: 0.8,
            ),
          ),
        ],
      ),
    );
  }
}
