/// Focus practice calendar sheet — GitHub-style heat + streak header.
library;

import 'package:flutter/material.dart';

import '../api/focus_practice_models.dart';
import '../state/focus_practice_controller.dart';

/// Emerald heat ramp on dark practice chrome (levels 0..4).
const List<Color> kFocusHeatColors = [
  Color(0xFF2A2A2A), // empty
  Color(0xFF1B4332),
  Color(0xFF2D6A4F),
  Color(0xFF40916C),
  Color(0xFF52B788),
];

Future<void> showPracticeFocusCalendarSheet({
  required BuildContext context,
  required FocusPracticeController focus,
}) {
  return showModalBottomSheet<void>(
    context: context,
    backgroundColor: const Color(0xFF1E1E1E),
    showDragHandle: true,
    isScrollControlled: true,
    builder: (ctx) {
      return AnimatedBuilder(
        animation: focus,
        builder: (context, _) => PracticeFocusCalendarSheet(focus: focus),
      );
    },
  );
}

class PracticeFocusCalendarSheet extends StatefulWidget {
  const PracticeFocusCalendarSheet({super.key, required this.focus});

  final FocusPracticeController focus;

  @override
  State<PracticeFocusCalendarSheet> createState() =>
      _PracticeFocusCalendarSheetState();
}

class _PracticeFocusCalendarSheetState extends State<PracticeFocusCalendarSheet> {
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
    final streak = focus.currentStreak;
    final best = focus.bestStreak;
    final milestone = focus.streakMilestone;
    final todayKey = focus.dayState.day;
    final theme = Theme.of(context);

    final first = DateTime(_month.year, _month.month, 1);
    final daysInMonth = DateTime(_month.year, _month.month + 1, 0).day;
    // Monday-first: weekday 1=Mon ... 7=Sun → index 0..6
    final lead = (first.weekday + 6) % 7;

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              '집중 기록',
              textAlign: TextAlign.center,
              style: theme.textTheme.titleMedium?.copyWith(
                color: Colors.white,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: _StatChip(
                    icon: Icons.local_fire_department,
                    label: '연속 $streak일',
                    accent: const Color(0xFFE67E22),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: _StatChip(
                    icon: Icons.emoji_events_outlined,
                    label: '최장 $best일',
                    accent: const Color(0xFFF1C40F),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: _StatChip(
                    icon: Icons.timer_outlined,
                    label: '오늘 ${focus.blocksCompletedToday}블록',
                    accent: const Color(0xFF52B788),
                  ),
                ),
              ],
            ),
            if (milestone != null) ...[
              const SizedBox(height: 10),
              Text(
                milestone >= 10
                    ? '참 잘했어요 · $milestone일 연속!'
                    : '$milestone일 연속 달성',
                textAlign: TextAlign.center,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: const Color(0xFF7DCEA0),
                ),
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
                    '${_month.year}.${_month.month.toString().padLeft(2, '0')}',
                    textAlign: TextAlign.center,
                    style: theme.textTheme.titleSmall?.copyWith(
                      color: Colors.white,
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
              children: const [
                _Dow('월'),
                _Dow('화'),
                _Dow('수'),
                _Dow('목'),
                _Dow('금'),
                _Dow('토'),
                _Dow('일'),
              ],
            ),
            const SizedBox(height: 6),
            GridView.builder(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 7,
                mainAxisSpacing: 6,
                crossAxisSpacing: 6,
              ),
              itemCount: lead + daysInMonth,
              itemBuilder: (context, i) {
                if (i < lead) return const SizedBox.shrink();
                final day = i - lead + 1;
                final key = focusPracticeDayKey(
                  DateTime(_month.year, _month.month, day),
                );
                final blocks = focus.envelope.blocksFor(key);
                final level = focusPracticeHeatLevel(blocks);
                final isToday = key == todayKey;
                return Tooltip(
                  message: blocks > 0 ? '$key · $blocks블록' : key,
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      color: kFocusHeatColors[level],
                      borderRadius: BorderRadius.circular(8),
                      border: isToday
                          ? Border.all(color: Colors.white70, width: 1.2)
                          : null,
                    ),
                    child: Center(
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Text(
                            '$day',
                            style: TextStyle(
                              color: level == 0
                                  ? Colors.white38
                                  : Colors.white,
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
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
                  ),
                );
              },
            ),
            const SizedBox(height: 14),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  '적음',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: Colors.white38,
                  ),
                ),
                const SizedBox(width: 8),
                for (var i = 0; i < kFocusHeatColors.length; i++) ...[
                  if (i > 0) const SizedBox(width: 4),
                  Container(
                    width: 14,
                    height: 14,
                    decoration: BoxDecoration(
                      color: kFocusHeatColors[i],
                      borderRadius: BorderRadius.circular(3),
                    ),
                  ),
                ],
                const SizedBox(width: 8),
                Text(
                  '많음',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: Colors.white38,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              '하루 1블록(10분 말하기)이면 연속에 포함됩니다.',
              textAlign: TextAlign.center,
              style: theme.textTheme.bodySmall?.copyWith(
                color: Colors.white38,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _StatChip extends StatelessWidget {
  const _StatChip({
    required this.icon,
    required this.label,
    required this.accent,
  });

  final IconData icon;
  final String label;
  final Color accent;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.white10,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(icon, size: 16, color: accent),
          const SizedBox(width: 4),
          Flexible(
            child: Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(color: Colors.white70, fontSize: 12),
            ),
          ),
        ],
      ),
    );
  }
}

class _Dow extends StatelessWidget {
  const _Dow(this.label);
  final String label;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Text(
        label,
        textAlign: TextAlign.center,
        style: const TextStyle(color: Colors.white38, fontSize: 11),
      ),
    );
  }
}
