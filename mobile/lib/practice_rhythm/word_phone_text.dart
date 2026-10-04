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
///
/// A hyphen joins two spoken words (`multi-walled`, `fuel-cell`), and each half
/// has its own phones, so the halves are split apart. The hyphen stays with the
/// first half so the printed line still reads the same.
List<WordPhone> wordPhonesFor({
  required String text,
  required List<FollowSpan> spans,
}) {
  final out = <WordPhone>[];
  for (final run in RegExp(r"\S+").allMatches(text)) {
    for (final piece in _hyphenPieces(text, run.start, run.end)) {
      var phone = '';
      for (final span in spans) {
        if (span.phone.trim().isEmpty) continue;
        if (span.start < piece.end && span.end > piece.start) {
          phone = span.phone.trim();
          break;
        }
      }
      out.add(WordPhone(
        start: piece.start,
        end: piece.end,
        word: text.substring(piece.start, piece.end),
        phone: phone,
      ));
    }
  }
  return out;
}

List<({int start, int end})> _hyphenPieces(String text, int start, int end) {
  final out = <({int start, int end})>[];
  var from = start;
  for (var i = start; i < end; i++) {
    final ch = text[i];
    final isHyphen = ch == '-' || ch == '\u2010' || ch == '\u2011';
    if (!isHyphen) continue;
    // A leading or trailing hyphen is not a join, and neither is `--`.
    if (i == from || i + 1 >= end) continue;
    out.add((start: from, end: i + 1));
    from = i + 1;
  }
  if (from < end) out.add((start: from, end: end));
  return out.isEmpty ? [(start: start, end: end)] : out;
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


/// design/384 — one span per sound, the ones the model did not hear picked out.
///
/// The word's own score cannot say which sound was missing, so a speaker about
/// to re-read the word had nothing to aim at. [sounds] is how sure the model was
/// of each symbol in [phone], in the same order, and anything under [line] is
/// drawn in [weak].
///
/// Returns one plain span when the two do not line up. A symbol the model's
/// vocabulary does not carry is dropped before scoring, and painting through
/// that gap would mark the wrong symbol — worse than marking none.
List<TextSpan> reviewSoundSpans({
  required String phone,
  required List<double> sounds,
  required double line,
  double bar = 1.0,
  // design/388 — stage one's pairs, same order as [sounds]. Not lined up and
  // every sound is judged by the line alone.
  List<List<SoundTop>> tops = const [],
  required Color weak,
  required Color strong,
}) {
  final symbols = [
    for (final one in phone.trim().split(RegExp(r'\s+')))
      if (one.isNotEmpty) one,
  ];
  if (symbols.isEmpty || symbols.length != sounds.length) {
    return [TextSpan(text: phone.trim(), style: TextStyle(color: strong))];
  }
  final out = <TextSpan>[];
  final lined = tops.length == sounds.length;
  for (var i = 0; i < symbols.length; i++) {
    final low = !soundClears(
      sounds[i],
      top: lined ? tops[i] : const [],
      bar: bar,
      line: line,
    );
    out.add(TextSpan(
      text: symbols[i],
      style: TextStyle(
        color: low ? weak : strong,
        fontWeight: low ? FontWeight.w700 : FontWeight.w400,
        decoration: low ? TextDecoration.underline : TextDecoration.none,
        decorationColor: weak,
        decorationThickness: 2.5,
      ),
    ));
    if (i + 1 < symbols.length) {
      out.add(TextSpan(text: '  ', style: TextStyle(color: strong)));
    }
  }
  return out;
}
