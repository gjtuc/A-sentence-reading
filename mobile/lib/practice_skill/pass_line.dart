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

/// How much of each new word is taken into the average.
///
/// Small on purpose. At 1% the last 300 words carry 95% of the average, which
/// measured the same as keeping an explicit window of the last 300 and costs
/// three numbers instead of three hundred.
const double kPassLineWeight = 0.01;

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
/// reader they are doing fine. Measured over real reading this never once bound,
/// so it costs nothing and only catches the case where something is wrong.
const double kPassLineFloor = 0.45;

/// Words needed before the account's own line is trusted.
///
/// Under this the fixed line is used, because an average over a handful of words
/// is mostly the accident of which words they were.
const int kPassLineWarmup = 40;

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

  /// This account after one more word.
  ///
  /// The weight is `1/n` while n is small, which makes the early average a plain
  /// running mean, and it slides into the 1% moving average on its own once n
  /// passes a hundred. Seeding the moving average with a single word instead
  /// would leave that one word steering the line for the next three hundred.
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
