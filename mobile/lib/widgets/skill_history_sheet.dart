/// design/412 - the practice rung's history, newest first.
library;

import 'package:flutter/material.dart';

import '../practice_skill/skill_history.dart';

String skillChangeWhenKo(int atMs) {
  final t = DateTime.fromMillisecondsSinceEpoch(atMs);
  String two(int n) => n.toString().padLeft(2, '0');
  return '${two(t.month)}.${two(t.day)} ${two(t.hour)}:${two(t.minute)}';
}

/// One line under the reason: the rung before and after, and what decided it.
String skillChangeDetailKo(SkillChange c) {
  final parts = <String>['${c.ladderBefore}/50 → ${c.ladderAfter}/50'];
  final avg = c.avg;
  if (avg != null) {
    final blocks = c.blocks > 0 ? ' (${c.blocks}블록)' : '';
    parts.add('평균 ${(avg * 100).round()}%$blocks');
    parts.add('기준 ${(c.lo * 100).round()}/${(c.hi * 100).round()}');
  }
  return parts.join(' · ');
}

Future<void> showSkillHistorySheet({
  required BuildContext context,
  required List<SkillChange> history,
}) {
  final rows = history.reversed.toList();
  return showModalBottomSheet<void>(
    context: context,
    backgroundColor: const Color(0xFF1E1E1E),
    showDragHandle: true,
    isScrollControlled: true,
    builder: (ctx) => SafeArea(
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.of(ctx).size.height * 0.75,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              '난이도 기록',
              style: Theme.of(ctx).textTheme.titleMedium?.copyWith(
                    color: Colors.white,
                  ),
            ),
            const SizedBox(height: 4),
            const Text(
              '평균이 아래 기준 이하면 쉽게, 위 기준 이상이면 어렵게 바뀝니다.',
              style: TextStyle(color: Colors.white38, fontSize: 11),
            ),
            const SizedBox(height: 8),
            Flexible(
              child: rows.isEmpty
                  ? const Padding(
                      padding: EdgeInsets.all(24),
                      child: Text(
                        '아직 기록이 없습니다.',
                        style: TextStyle(color: Colors.white54),
                      ),
                    )
                  : ListView.separated(
                      shrinkWrap: true,
                      padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                      itemCount: rows.length,
                      separatorBuilder: (_, __) =>
                          const Divider(height: 1, color: Colors.white12),
                      itemBuilder: (_, i) {
                        final c = rows[i];
                        return Padding(
                          padding: const EdgeInsets.symmetric(vertical: 8),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                '${skillChangeWhenKo(c.atMs)}   '
                                '${skillChangeReasonKo(c.reason)}',
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontSize: 13,
                                ),
                              ),
                              const SizedBox(height: 2),
                              Text(
                                skillChangeDetailKo(c),
                                style: const TextStyle(
                                  color: Colors.white54,
                                  fontSize: 12,
                                ),
                              ),
                            ],
                          ),
                        );
                      },
                    ),
            ),
          ],
        ),
      ),
    ),
  );
}
