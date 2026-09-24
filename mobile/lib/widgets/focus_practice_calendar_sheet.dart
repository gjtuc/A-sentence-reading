/// Month calendar heatmap for focus practice blocks + streak summary.
library;

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
            Text(
              '${focus.sentencesRead}',
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 22,
                fontWeight: FontWeight.w600,
              ),
            ),
            const Text(
              '읽은 문장 수',
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
              '색과 종이의 줄은 그날 완료한 ${kFocusPracticeBlockDuration.inMinutes}분 블록 수입니다.',
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
              _PageLines(lines: blocks),
          ],
        ),
      ),
    );
  }
}

/// Up to three lines fit on the tiny page. More blocks only deepen the green.
const int _kMaxPageLines = 3;

class _PageLines extends StatelessWidget {
  const _PageLines({required this.lines});

  final int lines;

  @override
  Widget build(BuildContext context) {
    final shown = lines < _kMaxPageLines ? lines : _kMaxPageLines;
    return CustomPaint(
      size: const Size(28, 22),
      painter: _OpenPagePainter(lines: shown),
    );
  }
}

class _OpenPagePainter extends CustomPainter {
  const _OpenPagePainter({required this.lines});

  final int lines;

  @override
  void paint(Canvas canvas, Size size) {
    final ink = Paint()
      ..color = const Color(0xFFF4F1E8)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 0.8
      ..strokeJoin = StrokeJoin.round;
    final w = size.width;
    final h = size.height;
    final mid = w * 0.48;
    final page = Path()
      ..moveTo(1, 2)
      ..lineTo(mid, 3.5)
      ..lineTo(w - 1, 1.5)
      ..lineTo(w - 2, h - 2)
      ..lineTo(mid, h - 3.5)
      ..lineTo(1.5, h - 1)
      ..close();
    canvas.drawPath(page, ink);
    canvas.drawLine(Offset(mid, 3.5), Offset(mid, h - 3.5), ink);
    final line = Paint()
      ..color = const Color(0xFFE7E2D6)
      ..strokeWidth = 0.7
      ..strokeCap = StrokeCap.round;
    for (var i = 0; i < lines; i++) {
      final y = 7.0 + i * 4.2;
      canvas.drawLine(Offset(4, y), Offset(mid - 3, y + 0.4), line);
    }
  }

  @override
  bool shouldRepaint(covariant _OpenPagePainter oldDelegate) =>
      oldDelegate.lines != lines;
}
