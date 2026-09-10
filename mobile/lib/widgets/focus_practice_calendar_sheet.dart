/// Month calendar heatmap for focus practice blocks + streak summary.
library;

import 'package:flutter/material.dart';

import '../api/focus_practice_models.dart';
import '../state/focus_practice_controller.dart';
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
}) {
  return showModalBottomSheet<void>(
    context: context,
    backgroundColor: const Color(0xFF1E1E1E),
    showDragHandle: true,
    isScrollControlled: true,
    builder: (ctx) {
      return AnimatedBuilder(
        animation: focus,
        builder: (context, _) => _FocusCalendarBody(focus: focus, skill: skill),
      );
    },
  );
}

class _FocusCalendarBody extends StatefulWidget {
  const _FocusCalendarBody({required this.focus, this.skill});

  final FocusPracticeController focus;
  final SkillStore? skill;

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

  @override
  Widget build(BuildContext context) {
    final focus = widget.focus;
    final todayKey = focusPracticeDayKey();
    final streak = focus.currentStreak;
    final best = focus.bestStreak;
    final todayBlocks = focus.blocksCompletedToday;
    final milestones = focusStreakMilestonesHit(streak);
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
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [
                _StatChip(label: '연속', value: '$streak일'),
                _StatChip(label: '최장', value: '$best일'),
                _StatChip(label: '오늘', value: '$todayBlocks블록'),
                _StatChip(
                  label: '인식',
                  value: () {
                    final sk = widget.skill;
                    if (sk == null) return '—';
                    final m = sk.dayMean(todayKey);
                    final n = sk.dayN(todayKey);
                    if (m == null || n < 3) return '—';
                    return '${(m * 100).round()}%';
                  }(),
                ),
              ],
            ),
            if (milestones.isNotEmpty) ...[
              const SizedBox(height: 10),
              Wrap(
                alignment: WrapAlignment.center,
                spacing: 6,
                runSpacing: 6,
                children: [
                  for (final m in milestones)
                    Chip(
                      visualDensity: VisualDensity.compact,
                      backgroundColor: const Color(0xFF2D5A3D),
                      label: Text(
                        m >= 10 ? '참 잘했어요 · $m일' : '$m일 연속',
                        style: const TextStyle(
                          color: Color(0xFF9BE9A8),
                          fontSize: 12,
                        ),
                      ),
                    ),
                ],
              ),
            ],
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
            Row(
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
              ],
            ),
            const SizedBox(height: 8),
            const Text(
              '색은 그날 완료한 10분 블록 수 · 연속은 하루 1블록 이상이면 이어집니다.',
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.white38, fontSize: 11),
            ),
          ],
        ),
      ),
    );
  }
}

class _StatChip extends StatelessWidget {
  const _StatChip({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(
          value,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
        ),
        Text(
          label,
          style: const TextStyle(color: Colors.white54, fontSize: 12),
        ),
      ],
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
      return const SizedBox(height: 40);
    }
    final dayNum = int.tryParse(dayKey!.substring(8, 10)) ?? 0;
    final level = focusHeatLevel(blocks);
    return Padding(
      padding: const EdgeInsets.all(2),
      child: Container(
        height: 40,
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
              Text(
                '$blocks',
                style: const TextStyle(
                  color: Colors.white70,
                  fontSize: 9,
                ),
              ),
          ],
        ),
      ),
    );
  }
}
