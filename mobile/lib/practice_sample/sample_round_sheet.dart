/// design/364 — pick which difficulty round of the sample set to read.
library;

import 'package:flutter/material.dart';

import '../api/tts_models.dart';
import '../practice_skill/skill_ladder.dart';
import 'sample_corpus.dart';
import 'sample_rounds.dart';

/// Round 1..10 maps onto ladder tier 0..9 at the middle density.
int sampleRoundTier(int round) => clampSkillTier(round - 1);

const int kSampleRoundDensity = 0;

/// Ladder number the round lands on, so the sheet and the calendar agree.
int sampleRoundLadderN(int round) => skillLadderDisplayN(
      tier: sampleRoundTier(round),
      density: kSampleRoundDensity,
    );

/// What the round will sound like: playback band and the accent mix.
String sampleRoundSubtitle(int round) {
  final tier = sampleRoundTier(round);
  final band = kTtsSkillTier[tier] ?? (0.7, 1.3);
  final weights = kTtsSkillLocaleWeights[tier] ?? const {'en-US': 1.0};
  final top = weights.entries.toList()
    ..sort((a, b) => b.value.compareTo(a.value));
  final accents = top
      .where((e) => e.value > 0)
      .take(2)
      .map((e) => '${_localeKo(e.key)} ${(e.value * 100).round()}%')
      .join(' · ');
  final lo = band.$1.toStringAsFixed(2);
  final hi = band.$2.toStringAsFixed(2);
  return '$lo~$hi배속 · $accents';
}

String _localeKo(String locale) {
  switch (locale) {
    case 'en-GB':
      return '영국';
    case 'en-AU':
      return '호주';
    case 'en-IN':
      return '인도';
    default:
      return '미국';
  }
}

/// Returns the chosen round, or null when dismissed.
Future<int?> showSampleRoundSheet(
  BuildContext context, {
  required SampleRounds rounds,
}) {
  return showModalBottomSheet<int>(
    context: context,
    isScrollControlled: true,
    builder: (ctx) => _SampleRoundSheet(rounds: rounds),
  );
}

class _SampleRoundSheet extends StatelessWidget {
  const _SampleRoundSheet({required this.rounds});

  final SampleRounds rounds;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(8, 12, 8, 16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: Text(
                '$kSampleTitle · ${rounds.doneCount}/$kSampleRoundCount',
                style: theme.textTheme.titleMedium,
              ),
            ),
            const SizedBox(height: 4),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: Text(
                '같은 문장 ${kSampleFixedLines.length}개에 새 문장 '
                '$kSampleFreshPerRound개. 난이도만 바뀝니다. '
                '한 판이 끝나면 저절로 멈춥니다.',
                style: theme.textTheme.bodySmall,
              ),
            ),
            const SizedBox(height: 8),
            Flexible(
              child: ListView.builder(
                shrinkWrap: true,
                itemCount: kSampleRoundCount,
                itemBuilder: (ctx, i) {
                  final round = i + 1;
                  final done = rounds.isDone(round);
                  final takes = rounds.takesFor(round);
                  final target = sampleRoundTarget(round);
                  return ListTile(
                    leading: Icon(
                      done
                          ? Icons.check_circle
                          : (takes > 0
                              ? Icons.radio_button_checked
                              : Icons.radio_button_unchecked),
                      color: done ? theme.colorScheme.primary : null,
                    ),
                    title: Text(
                      '난이도 $round '
                      '(${sampleRoundLadderN(round)}/$kSkillLadderTotal)',
                    ),
                    subtitle: Text(sampleRoundSubtitle(round)),
                    trailing: Text(
                      '$takes/$target',
                      style: theme.textTheme.bodySmall,
                    ),
                    onTap: () => Navigator.of(ctx).pop(round),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}
