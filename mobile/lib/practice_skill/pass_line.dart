/// Where the pass line sits for this account. design/371.
///
/// A fixed line cannot be fair. The same reader, the same care, and the same
/// mouth score differently on a long word than a short one, and differently
/// again on a paper full of names. Measured on 2,924 words of real reading, the
/// fixed 0.72 the app shipped with sent 38% of correctly-read words to practice.
///
/// So the line is drawn from the account's own reading instead: a little below
/// its own average. What counts as "a little" is the account's own spread, so a
/// reader whose scores sit in a tight band is held to a tight band, and one
/// whose scores swing is not punished for swinging.
library;

import 'dart:math' as math;

/// design/388 — the line's samples are sounds, and a judged word holds this
/// many on average over the 2,924 words of real reading
/// (scripts/spread_overlap_probe.py). The weight and the warm-up below are
/// counted in sounds so that they stay the same in words.
const double kPassLineSoundsPerWord = 5.73;

/// How much of each new sound is taken into the average: 1% per word.
///
/// Small on purpose. At 1% a word, the last 300 words carry 95% of the average,
/// which measured the same as keeping an explicit window of the last 300 and
/// costs three numbers instead of three hundred.
const double kPassLineWeight = 0.01 / kPassLineSoundsPerWord;

/// How far below the average the line sits, counted in spreads.
///
/// Measured over real reading: -0.5 keeps 75% of correct words and catches 53%
/// of wrong ones, -0.75 keeps 81% and catches 47%, -1.0 keeps 85% and catches
/// 38%. Against the fixed line's 62% and 64%.
const double kPassLineOffset = -0.75;

/// The lowest the line may go, however the account has been reading.
///
/// Without this a broken microphone teaches the account that 0.1 is normal, the
/// line follows it down, and the app starts passing everything while telling the
/// reader they are doing fine. Over the design/371 word overlap it never once
/// bound. design/388 — over the spread overlap of single sounds it usually
/// does: a sound mostly lands near 0 or near 1, so the spread is wide and the
/// formula falls under it.
const double kPassLineFloor = 0.45;

/// The line to judge by before the account has one of its own. design/375·388.
///
/// Not a number chosen on its own. It is [kPassLineOffset] spreads below the
/// average — the same formula the account uses — with the population's numbers
/// standing in for the account's: mean 0.680, spread 0.370 over all 16,759
/// sounds of real reading the scorer could ask about, each one's spread
/// overlap. That is 0.403, under [kPassLineFloor], so the floor is the line,
/// exactly as it would be for an account reading like that. Measured without
/// looking at any label, so it is a description of how this scorer scores,
/// not a fit to what anyone decided was right.
///
/// design/375's 0.57 was the same formula over the design/371 word overlap, a
/// different number; carried over it would have judged a spread overlap by
/// another ruler's average.
const double kPassLineCold = 0.45;

/// design/388 — what the samples behind a stored line are: one sound's spread
/// overlap each. A line stored under any other unit is dropped rather than
/// carried, because an average of design/386 match fractions says nothing about
/// where an overlap should be cut.
const int kPassLineUnit = 388;

/// Sounds needed before the account's own line is trusted: forty words at
/// [kPassLineSoundsPerWord].
///
/// Under this the fixed line is used, because an average over a handful of words
/// is mostly the accident of which words they were.
const int kPassLineWarmup = 229;

/// An account's average score and spread, and how many words are behind them.
///
/// Three numbers. Nothing per-word is kept, so practising for a year costs the
/// same storage as practising for a day.
class PassLine {
  const PassLine({this.avg = 0, this.varp = 0, this.n = 0});

  final double avg;

  /// Spread as a variance, so updating it needs no square root.
  final double varp;
  final int n;

  bool get warm => n >= kPassLineWarmup;

  double get spread => math.sqrt(math.max(varp, 0));

  /// The line to judge a word against, given the fixed line to use while cold.
  double lineOr(double cold) => warm
      ? math.max(avg + kPassLineOffset * spread, kPassLineFloor)
      : cold;

  /// This account after one more sound. design/388.
  ///
  /// The weight is `1/n` while n is small, which makes the early average a plain
  /// running mean, and it slides into the moving average on its own once n
  /// passes `1/kPassLineWeight`, a hundred words. Seeding the moving average
  /// with a single sound instead would leave it steering the line for the next
  /// three hundred words.
  PassLine after(double score) {
    final next = n + 1;
    if (next == 1) return PassLine(avg: score, varp: 0, n: 1);
    final w = math.max(kPassLineWeight, 1.0 / next);
    final gap = score - avg;
    return PassLine(
      avg: avg + w * gap,
      varp: (1 - w) * (varp + w * gap * gap),
      n: next,
    );
  }

  /// This account after a whole take.
  PassLine afterAll(Iterable<double> scores) {
    var out = this;
    for (final score in scores) {
      out = out.after(score);
    }
    return out;
  }
}
