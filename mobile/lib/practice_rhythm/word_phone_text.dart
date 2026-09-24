/// Sentence with each word's pronunciation symbols under that word.
library;

import 'package:flutter/material.dart';

import '../practice_skill/skill_score.dart';
import 'follow_span.dart';
import 'replay_miss_text.dart';
import 'rhythm_theme.dart';

/// One printed word plus the phones for it. Empty [phone] draws no second line.
class WordPhone {
  const WordPhone({
    required this.start,
    required this.end,
    required this.word,
    required this.phone,
  });

  final int start;
  final int end;
  final String word;
  final String phone;
}

/// Printed words in order, each carrying the phones of the span that covers it.
List<WordPhone> wordPhonesFor({
  required String text,
  required List<FollowSpan> spans,
}) {
  final out = <WordPhone>[];
  final words = RegExp(r"\S+").allMatches(text);
  for (final word in words) {
    var phone = '';
    for (final span in spans) {
      if (span.phone.trim().isEmpty) continue;
      if (span.start < word.end && span.end > word.start) {
        phone = span.phone.trim();
        break;
      }
    }
    out.add(WordPhone(
      start: word.start,
      end: word.end,
      word: text.substring(word.start, word.end),
      phone: phone,
    ));
  }
  return out;
}

class WordPhoneText extends StatelessWidget {
  const WordPhoneText({
    super.key,
    required this.text,
    required this.spans,
    required this.style,
    this.misses = const [],
    this.follow,
    this.markAlpha = 0.0,
  });

  final String text;
  final List<FollowSpan> spans;
  final TextStyle style;
  final List<MissedWordSpan> misses;
  final ({int start, int end})? follow;

  /// 0 draws no practice marker. The replay blink drives this.
  final double markAlpha;

  @override
  Widget build(BuildContext context) {
    final phoneStyle = (Theme.of(context).textTheme.bodySmall ?? const TextStyle())
        .copyWith(color: kRhythmText.withValues(alpha: 0.7));
    final words = wordPhonesFor(text: text, spans: spans);
    return Wrap(
      alignment: WrapAlignment.center,
      crossAxisAlignment: WrapCrossAlignment.start,
      spacing: 10,
      runSpacing: 6,
      children: [
        for (final item in words)
          Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                item.word,
                style: style.copyWith(
                  color: _lit(item) ? kRhythmSpeak : style.color,
                  backgroundColor: _marked(item)
                      ? kPracticeMark.withValues(alpha: markAlpha)
                      : null,
                ),
              ),
              if (item.phone.isNotEmpty)
                Text(item.phone, style: phoneStyle),
            ],
          ),
      ],
    );
  }

  bool _lit(WordPhone item) {
    final span = follow;
    if (span == null) return false;
    return span.start < item.end && span.end > item.start;
  }

  bool _marked(WordPhone item) {
    if (markAlpha <= 0) return false;
    for (final miss in misses) {
      if (miss.start < item.end && miss.end > item.start) return true;
    }
    return false;
  }
}
