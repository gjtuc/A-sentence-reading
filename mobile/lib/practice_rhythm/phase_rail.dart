/// design/214 — Listen · Speak · Replay phase rail.
library;

import 'package:flutter/material.dart';

import 'rhythm_theme.dart';

class RhythmPhaseRail extends StatefulWidget {
  const RhythmPhaseRail({
    super.key,
    required this.phase,
  });

  final RhythmPhase phase;

  @override
  State<RhythmPhaseRail> createState() => _RhythmPhaseRailState();
}

class _RhythmPhaseRailState extends State<RhythmPhaseRail>
    with SingleTickerProviderStateMixin {
  late final AnimationController _pulse;

  static const _labels = ['Listen', 'Speak', 'Replay'];

  int get _activeIndex {
    switch (widget.phase) {
      case RhythmPhase.listen:
        return 0;
      case RhythmPhase.speak:
        return 1;
      case RhythmPhase.replay:
        return 2;
      case RhythmPhase.idle:
        return -1;
    }
  }

  @override
  void initState() {
    super.initState();
    _pulse = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    );
    _syncPulse();
  }

  @override
  void didUpdateWidget(covariant RhythmPhaseRail oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.phase != widget.phase) _syncPulse();
  }

  void _syncPulse() {
    if (widget.phase == RhythmPhase.speak) {
      if (!_pulse.isAnimating) _pulse.repeat(reverse: true);
    } else {
      _pulse.stop();
      _pulse.value = 0;
    }
  }

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final active = _activeIndex;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        AnimatedBuilder(
          animation: _pulse,
          builder: (context, _) {
            return Row(
              children: List.generate(3, (i) {
                final on = i == active;
                final accent =
                    on ? rhythmAccentFor(widget.phase) : kRhythmRailIdle;
                final speakBoost = on &&
                    widget.phase == RhythmPhase.speak &&
                    _pulse.isAnimating;
                final h = speakBoost ? 3.0 + 2.0 * _pulse.value : 3.0;
                return Expanded(
                  child: Padding(
                    padding: EdgeInsets.only(
                      left: i == 0 ? 0 : 4,
                      right: i == 2 ? 0 : 4,
                    ),
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 160),
                      height: h,
                      decoration: BoxDecoration(
                        color: accent.withValues(
                          alpha: speakBoost ? 0.55 + 0.45 * _pulse.value : 1,
                        ),
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                  ),
                );
              }),
            );
          },
        ),
        const SizedBox(height: 6),
        Row(
          children: List.generate(3, (i) {
            final on = i == active;
            return Expanded(
              child: Text(
                _labels[i],
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 11,
                  letterSpacing: 0.4,
                  fontWeight: on ? FontWeight.w600 : FontWeight.w400,
                  color: on
                      ? kRhythmText
                      : kRhythmTextMuted.withValues(alpha: 0.55),
                ),
              ),
            );
          }),
        ),
      ],
    );
  }
}
