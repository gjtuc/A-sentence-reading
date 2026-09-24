/// Month calendar heatmap for focus practice blocks + streak summary.
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../api/focus_practice_models.dart';
import '../state/focus_practice_controller.dart';
import '../practice_skill/skill_ladder.dart';
import '../practice_skill/skill_store.dart';

/// Single emerald palette · level 0..3 (empty → densest).
Color focusHeatColor(int level, {required bool dark}) {
  switch (level) {
    case 1:
      return dark ? const Color(0xFF2D5A3D) : const Color(0xFF9BE9A8);
    case 2:
      return dark ? const Color(0xFF3D8B57) : const Color(0xFF40C463);
    case 3:
      return dark ? const Color(0xFF56D364) : const Color(0xFF216E39);
    default:
      return dark ? const Color(0xFF2A2A2A) : const Color(0xFFEBEDF0);
  }
}

Future<void> showFocusPracticeCalendarSheet({
  required BuildContext context,
  required FocusPracticeController focus,
  SkillStore? skill,
  bool skillFeatureOn = true,
}) {
  return showModalBottomSheet<void>(
    context: context,
    backgroundColor: const Color(0xFF1E1E1E),
    showDragHandle: true,
    isScrollControlled: true,
    builder: (ctx) {
      return AnimatedBuilder(
        animation: focus,
        builder: (context, _) => _FocusCalendarBody(
          focus: focus,
          skill: skill,
          skillFeatureOn: skillFeatureOn,
        ),
      );
    },
  );
}

class _FocusCalendarBody extends StatefulWidget {
  const _FocusCalendarBody({
    required this.focus,
    this.skill,
    this.skillFeatureOn = true,
  });

  final FocusPracticeController focus;
  final SkillStore? skill;
  final bool skillFeatureOn;

  @override
  State<_FocusCalendarBody> createState() => _FocusCalendarBodyState();
}

class _FocusCalendarBodyState extends State<_FocusCalendarBody> {
  late DateTime _month;

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    _month = DateTime(now.year, now.month);
  }

  void _shiftMonth(int delta) {
    setState(() {
      _month = DateTime(_month.year, _month.month + delta);
    });
  }

  String _difficultyAndRecognition() {
    final sk = widget.skill;
    final difficulty = (sk == null || !widget.skillFeatureOn)
        ? '난이도 —'
        : skillLadderLabelKo(tier: sk.state.tier, density: sk.state.density);
    if (sk == null) return '$difficulty · 인식 —';
    final todayKey = focusPracticeDayKey();
    final mean = sk.dayMean(todayKey);
    final n = sk.dayN(todayKey);
    final recognition =
        (mean == null || n < 3) ? '인식 —' : '인식 ${(mean * 100).round()}%';
    return '$difficulty · $recognition';
  }

  @override
  Widget build(BuildContext context) {
    final focus = widget.focus;
    final todayKey = focusPracticeDayKey();
    final cells = focusMonthCellKeys(_month.year, _month.month);
    final title = '${_month.year}.${_month.month.toString().padLeft(2, '0')}';

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              '연습 캘린더',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    color: Colors.white,
                  ),
            ),
            const SizedBox(height: 12),
            const Text(
              '0원',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.white,
                fontSize: 22,
                fontWeight: FontWeight.w600,
              ),
            ),
            const Text(
              '쌓인 기부금',
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.white54, fontSize: 12),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                IconButton(
                  onPressed: () => _shiftMonth(-1),
                  icon: const Icon(Icons.chevron_left, color: Colors.white70),
                ),
                Expanded(
                  child: Text(
                    title,
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
                IconButton(
                  onPressed: () => _shiftMonth(1),
                  icon: const Icon(Icons.chevron_right, color: Colors.white70),
                ),
              ],
            ),
            const SizedBox(height: 4),
            Row(
              children: [
                for (final w in const ['일', '월', '화', '수', '목', '금', '토'])
                  Expanded(
                    child: Text(
                      w,
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                        color: Colors.white38,
                        fontSize: 11,
                      ),
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 6),
            for (var row = 0; row < cells.length / 7; row++)
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Row(
                  children: [
                    for (var col = 0; col < 7; col++)
                      Expanded(
                        child: _DayCell(
                          dayKey: cells[row * 7 + col],
                          blocks: cells[row * 7 + col] == null
                              ? 0
                              : focus.history.blocksFor(cells[row * 7 + col]!),
                          isToday: cells[row * 7 + col] == todayKey,
                        ),
                      ),
                  ],
                ),
              ),
            const SizedBox(height: 12),
            FittedBox(
              fit: BoxFit.scaleDown,
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Text(
                    '적음',
                    style: TextStyle(color: Colors.white38, fontSize: 11),
                  ),
                  const SizedBox(width: 6),
                  for (var lv = 0; lv <= 3; lv++) ...[
                    Container(
                      width: 12,
                      height: 12,
                      margin: const EdgeInsets.symmetric(horizontal: 2),
                      decoration: BoxDecoration(
                        color: focusHeatColor(lv, dark: true),
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                  ],
                  const SizedBox(width: 6),
                  const Text(
                    '많음',
                    style: TextStyle(color: Colors.white38, fontSize: 11),
                  ),
                  const SizedBox(width: 10),
                  const Text(
                    '·',
                    style: TextStyle(color: Colors.white38, fontSize: 11),
                  ),
                  const SizedBox(width: 10),
                  Text(
                    _difficultyAndRecognition(),
                    style: const TextStyle(
                      color: Colors.white54,
                      fontSize: 11,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 8),
            Text(
              '색과 동전은 그날 완료한 ${kFocusPracticeBlockDuration.inMinutes}분 블록 수입니다.',
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.white38, fontSize: 11),
            ),
          ],
        ),
      ),
    );
  }
}

class _DayCell extends StatelessWidget {
  const _DayCell({
    required this.dayKey,
    required this.blocks,
    required this.isToday,
  });

  final String? dayKey;
  final int blocks;
  final bool isToday;

  @override
  Widget build(BuildContext context) {
    if (dayKey == null) {
      return const SizedBox(height: 56);
    }
    final dayNum = int.tryParse(dayKey!.substring(8, 10)) ?? 0;
    final level = focusHeatLevel(blocks);
    return Padding(
      padding: const EdgeInsets.all(2),
      child: Container(
        height: 56,
        decoration: BoxDecoration(
          color: focusHeatColor(level, dark: true),
          borderRadius: BorderRadius.circular(6),
          border: isToday
              ? Border.all(color: Colors.white70, width: 1.2)
              : null,
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(
              '$dayNum',
              style: TextStyle(
                color: level == 0 ? Colors.white38 : Colors.white,
                fontSize: 12,
                fontWeight: FontWeight.w500,
              ),
            ),
            if (blocks > 0)
              _CoinPile(dayKey: dayKey!, blocks: blocks),
          ],
        ),
      ),
    );
  }
}

/// Visible coins stop at four. The green cell keeps darkening after that.
const int _kMaxVisibleCoins = 4;

int _dayPileSeed(String dayKey) {
  var h = 2166136261;
  for (final c in dayKey.codeUnits) {
    h ^= c;
    h = (h * 16777619) & 0x7fffffff;
  }
  return h;
}

class _CoinPile extends StatelessWidget {
  const _CoinPile({required this.dayKey, required this.blocks});

  final String dayKey;
  final int blocks;

  @override
  Widget build(BuildContext context) {
    final shown = blocks < _kMaxVisibleCoins ? blocks : _kMaxVisibleCoins;
    final seed = _dayPileSeed(dayKey);
    return SizedBox(
      height: 26,
      width: 30,
      child: Stack(
        alignment: Alignment.bottomCenter,
        children: [
          for (var i = 0; i < shown; i++)
            Positioned(
              bottom: i * 3.4,
              left: 0,
              right: 0,
              child: Transform.translate(
                offset: Offset(_coinDx(seed, i), 0),
                child: Transform.rotate(
                  angle: _coinAngle(seed, i),
                  child: const Center(child: _Coin(size: 13)),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

double _coinDx(int seed, int index) {
  final v = (seed >> (index * 4)) & 7;
  return (v - 3) * 0.65;
}

double _coinAngle(int seed, int index) {
  final v = (seed >> (10 + index * 3)) & 7;
  return (v - 3) * 0.06;
}

class _Coin extends StatelessWidget {
  const _Coin({required this.size});

  final double size;

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      size: Size(size, size),
      painter: const _MintedCoinPainter(),
    );
  }
}

/// Rim, thickness, inner ring, and a top highlight. Those four read at this size.
class _MintedCoinPainter extends CustomPainter {
  const _MintedCoinPainter();

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width;
    final face = Rect.fromLTWH(0, 0, w, w * 0.82);
    final edge = Rect.fromLTWH(0, w * 0.18, w, w * 0.82);
    canvas.drawOval(edge, Paint()..color = const Color(0xFF6A420C));
    canvas.drawOval(
      Rect.fromLTWH(w * 0.05, w * 0.24, w * 0.9, w * 0.68),
      Paint()..color = const Color(0xFFC8962E),
    );
    canvas.drawOval(
      face,
      Paint()
        ..shader = const RadialGradient(
          center: Alignment(-0.32, -0.5),
          radius: 0.95,
          colors: [
            Color(0xFFFFF8D6),
            Color(0xFFF3CC62),
            Color(0xFFE0A428),
            Color(0xFFB67A14),
          ],
          stops: [0, 0.42, 0.72, 1],
        ).createShader(face),
    );
    canvas.drawOval(
      face.deflate(w * 0.02),
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = w * 0.07
        ..color = const Color(0xFF8A5C12),
    );
    canvas.drawOval(
      face.deflate(w * 0.16),
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = w * 0.035
        ..color = const Color(0xAAFFF3C2),
    );
    final center = face.center;
    final reed = Paint()
      ..color = const Color(0x99604010)
      ..strokeWidth = 0.45
      ..strokeCap = StrokeCap.round;
    for (var i = 0; i < 12; i++) {
      final a = i * math.pi * 2 / 12;
      final inner = w * 0.34;
      final outer = w * 0.40;
      canvas.drawLine(
        center + Offset(math.cos(a) * inner, math.sin(a) * inner * 0.82),
        center + Offset(math.cos(a) * outer, math.sin(a) * outer * 0.82),
        reed,
      );
    }
    canvas.drawOval(
      Rect.fromCircle(center: Offset(w * 0.36, w * 0.24), radius: w * 0.11),
      Paint()..color = const Color(0xF2FFF9DE),
    );
  }

  @override
  bool shouldRepaint(covariant _MintedCoinPainter oldDelegate) => false;
}
